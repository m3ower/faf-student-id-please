"""Disposable real Player/Session -> HTTP -> ETL -> PostgreSQL acceptance check.

Requires locally built export-capable images. Uses only synthetic rows and newly
created containers/network. No shared stack, environment files or production DBs.
"""
import argparse
import json
import secrets
import subprocess
from uuid import uuid4


def docker(*args, check=True):
    try:
        result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Isolated Docker verification timed out") from None
    if check and result.returncode:
        # Commands may contain ephemeral credentials. Never print command/stderr.
        raise RuntimeError("Isolated Docker verification failed") from None
    return result


def verify(player_image, session_image, etl_image):
    prefix = "warehouse-check-" + uuid4().hex[:10]
    pg, player, session, network = (prefix + suffix for suffix in ("-pg", "-player", "-session", "-net"))
    password, ptoken, stoken = (secrets.token_urlsafe(32) for _ in range(3))
    player_id, session_id, team_id = (str(uuid4()) for _ in range(3))
    def command(database, query):
        return docker("exec", pg, "psql", "-U", "lab_test", "-d", database, "-v", "ON_ERROR_STOP=1", "-Atc", query).stdout.strip()
    try:
        docker("network", "create", network)
        docker("run", "-d", "--name", pg, "--network", network,
               "-e", "POSTGRES_USER=lab_test", "-e", "POSTGRES_PASSWORD="+password, "postgres:16-alpine")
        # Wait for final postmaster (the initialization server has no TCP listener).
        import time
        deadline = time.monotonic()+60
        while docker("exec", pg, "pg_isready", "-h", "127.0.0.1", "-U", "lab_test", check=False).returncode:
            if time.monotonic()>deadline: raise RuntimeError("Test database did not start")
            time.sleep(.2)
        for database in ("player_test", "session_test", "warehouse_test"):
            command("postgres", "CREATE DATABASE "+database)
        # Respect Player's production signing requirement. The builder image is
        # already required by its Dockerfile. Capture this ephemeral key privately;
        # it is never supplied to ETL or printed in verification output.
        generate_key = '''cat > /tmp/FixtureKey.java <<'JAVA'
import java.security.KeyPairGenerator;
import java.util.Base64;
class FixtureKey {
 public static void main(String[] args) throws Exception {
  var generator=KeyPairGenerator.getInstance("RSA");generator.initialize(2048);
  String pem="-----BEGIN PRIVATE KEY-----\\n"+Base64.getEncoder().encodeToString(generator.generateKeyPair().getPrivate().getEncoded())+"\\n-----END PRIVATE KEY-----";
  System.out.print(Base64.getEncoder().encodeToString(pem.getBytes(java.nio.charset.StandardCharsets.US_ASCII)));
 }
}
JAVA
java /tmp/FixtureKey.java'''
        key = docker("run", "--rm", "--entrypoint", "sh", "maven:3.9-eclipse-temurin-21", "-c", generate_key).stdout.strip()
        docker("run", "-d", "--name", player, "--network", network, "--network-alias", "player-service",
               "-e", f"PLAYER_DB_URL=jdbc:postgresql://{pg}:5432/player_test", "-e", "PLAYER_DB_USER=lab_test",
               "-e", "PLAYER_DB_PASSWORD="+password, "-e", "WAREHOUSE_EXPORT_TOKEN="+ptoken,
               "-e", "PLAYER_INTERNAL_TOKEN="+secrets.token_urlsafe(32),
               "-e", "BROKER_SERVICE_TOKEN="+secrets.token_urlsafe(32), "-e", "PLAYER_JWT_PRIVATE_KEY_B64="+key, player_image)
        docker("run", "-d", "--name", session, "--network", network, "--network-alias", "session-service",
               "-e", f"SESSION_DB_URL=postgres://lab_test:{password}@{pg}:5432/session_test?sslmode=disable",
               "-e", "SESSION_INTERNAL_TOKEN="+secrets.token_urlsafe(32), "-e", "BROKER_SERVICE_TOKEN="+secrets.token_urlsafe(32),
               "-e", "WAREHOUSE_EXPORT_TOKEN="+stoken, session_image)
        wait = '''
import time, urllib.request
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for host in ("player-service", "session-service"):
    end=time.monotonic()+60
    while True:
        try:
            with opener.open("http://"+host+":8080/health/ready",timeout=2) as r:
                assert r.status==200
            break
        except Exception:
            if time.monotonic()>end: raise RuntimeError("Owned test service did not become ready") from None
            time.sleep(.2)
'''
        docker("run", "--rm", "--network", network, "--entrypoint", "python", etl_image, "-c", wait)
        # Test fixture setup only. ETL itself receives no source database credentials.
        command("player_test", f"INSERT INTO players(id,username,email,password_hash,level,xp,shifts_completed,accuracy_total,disciplinary_actions) VALUES('{player_id}','synthetic-warehouse','synthetic@example.test','unused-test-only',1,100,1,1,0)")
        command("session_test", f"INSERT INTO moderation_sessions(id,team_id,host_player_id,difficulty,state) VALUES('{session_id}','{team_id}','{player_id}','NORMAL','LOBBY')")
        def batch(run_id, expected=0):
            result = docker("run", "--rm", "--network", network,
                "-e", "PGHOST="+pg, "-e", "PGDATABASE=warehouse_test", "-e", "PGUSER=lab_test", "-e", "PGPASSWORD="+password,
                "-e", "PLAYER_WAREHOUSE_EXPORT_TOKEN="+ptoken, "-e", "SESSION_WAREHOUSE_EXPORT_TOKEN="+stoken,
                "-e", "ETL_RUN_ID="+run_id, etl_image, check=False)
            if result.returncode != expected: raise RuntimeError("Live export/load result was unexpected")
            return json.loads(result.stdout)
        first = str(uuid4())
        assert batch(first)["rows"]==2
        assert batch(first)["replayed"]
        assert command("warehouse_test", "SELECT xp FROM player_progression")=="100"
        assert command("warehouse_test", "SELECT count(*) FROM session_results")=="1"
        command("player_test", f"UPDATE players SET xp=200 WHERE id='{player_id}'")
        batch(str(uuid4()))
        assert command("warehouse_test", "SELECT xp FROM player_progression")=="200"
        command("player_test", f"DELETE FROM players WHERE id='{player_id}'")
        batch(str(uuid4()))
        assert command("warehouse_test", "SELECT count(*) FROM player_progression")=="0"
        docker("stop", "--time", "3", session)
        assert batch(str(uuid4()), expected=1)["event"]=="etl_failed"
        assert command("warehouse_test", "SELECT count(*) FROM warehouse_runs")=="3"
        assert command("warehouse_test", "SELECT count(*) FROM session_results")=="1"
        print(json.dumps({"verification":"passed", "sources":2, "successfulBatches":3,
                          "replay":"passed", "updatesAndDeletion":"passed", "failedSourcePreservesWarehouse":"passed"}))
    finally:
        for name in (player,session,pg): docker("rm", "--force", "--volumes", name, check=False)
        docker("network", "rm", network, check=False)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--player-image", default="student-id-player-service:warehouse-local")
    parser.add_argument("--session-image", default="student-id-session-service:warehouse-local")
    parser.add_argument("--etl-image", default="student-id-warehouse-etl:local")
    args=parser.parse_args()
    verify(args.player_image,args.session_image,args.etl_image)
