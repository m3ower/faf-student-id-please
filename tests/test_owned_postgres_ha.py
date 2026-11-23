"""Security/adoption boundaries of the opt-in owned Patroni configuration."""
import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location("owned_ha_start",Path(__file__).resolve().parents[1]/"docker/owned-postgres-ha/start.py")
MODULE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MODULE)

class OwnedHAConfigTest(unittest.TestCase):
 def settings(self):
  return {"HA_NAME":"applicant-db","HA_SCOPE":"applicant","HA_ETCD_HOSTS":"etcd-1:2379,etcd-2:2379,etcd-3:2379",
          "HA_APP_USER":"applicant_user","HA_APP_DATABASE":"applicant_db",
          **{"HA_"+key+"_PASSWORD":key.lower()+"x"*40 for key in ("ADMIN","REPLICATION","REST","APP")}}
 def test_scopes_storage_and_credentials_are_separate(self):
  env=self.settings();c=MODULE.configuration(env)
  self.assertEqual(c['postgresql']['data_dir'],'/var/lib/postgresql/ha/data')
  self.assertNotIn('/var/lib/postgresql/data',str(c))
  self.assertEqual(c['restapi']['authentication']['password'],env['HA_REST_PASSWORD'])
  self.assertEqual(c['postgresql']['authentication']['replication']['password'],env['HA_REPLICATION_PASSWORD'])
  self.assertNotIn(env['HA_APP_PASSWORD'],str(c))
  self.assertFalse(c['postgresql']['remove_data_directory_on_rewind_failure'])
  self.assertFalse(c['postgresql']['remove_data_directory_on_diverged_timelines'])
  self.assertTrue(c['bootstrap']['dcs']['check_timeline'])
  env['HA_SCOPE']='record';self.assertEqual(MODULE.configuration(env)['scope'],'record')
 def test_invalid_or_reused_credentials_fail_before_startup(self):
  for key in ('HA_ADMIN_PASSWORD','HA_REPLICATION_PASSWORD','HA_REST_PASSWORD','HA_APP_PASSWORD'):
   for value in ('','x'*31,'x'*257,'x'*40+'!'):
    with self.subTest(key=key,length=len(value)):
     env=self.settings();env[key]=value
     with self.assertRaises(ValueError):MODULE.configuration(env)
  env=self.settings();env['HA_ADMIN_PASSWORD']=env['HA_APP_PASSWORD']
  with self.assertRaises(ValueError):MODULE.configuration(env)
 def test_scope_host_and_identifier_injection_are_rejected(self):
  for key,value in [('HA_SCOPE','moderation'),('HA_NAME','bad/host'),('HA_ETCD_HOSTS','http://evil:2379'),('HA_ETCD_HOSTS','etcd-1:2379'),('HA_APP_USER','user;drop'),('HA_APP_DATABASE','../old')]:
   with self.subTest(key=key):
    env=self.settings();env[key]=value
    with self.assertRaises(ValueError):MODULE.configuration(env)

if __name__=='__main__':unittest.main()
