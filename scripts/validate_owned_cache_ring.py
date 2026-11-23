"""Independent oracle for the documented Java/Go ring vectors and movement properties."""
import bisect
import hashlib
import json
from pathlib import Path


def validate():
    root=Path(__file__).resolve().parents[1]
    fixture=json.loads((root/'contracts/cache/hash-ring-v1.json').read_text(encoding='utf-8'))
    def hashed(value):return hashlib.sha256(('owned-cache-ring-v1\n'+value).encode()).hexdigest()
    def ring(ids):return sorted((hashed('node\n'+id+'\n'+str(i)),id) for id in ids for i in range(128))
    def owner(points,key):return points[bisect.bisect_left([p[0] for p in points],hashed('key\n'+key))%len(points)][1]
    three=ring(fixture['nodes']);four=ring(['a','b','c','d']);two=ring(['a','b'])
    assert fixture['algorithm']=='owned-cache-ring-v1' and fixture['virtualNodes']==128
    for v in fixture['vectors']:assert owner(three,v['key'])==v['owner']
    distribution={id:0 for id in fixture['nodes']};added=removed=0
    for i in range(20000):
        key='population-'+str(i);old,new,less=owner(three,key),owner(four,key),owner(two,key);distribution[old]+=1
        if new!=old:assert new=='d';added+=1
        if less!=old:assert old=='c';removed+=1
    assert all(4500<n<9000 for n in distribution.values()) and 3000<added<7000
    print(json.dumps({'vectors':len(fixture['vectors']),'keys':20000,'distribution':distribution,'addedMoved':added,'removedMoved':removed}))


if __name__=='__main__':validate()
