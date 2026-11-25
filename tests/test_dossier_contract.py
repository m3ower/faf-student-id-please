"""Dossier grants and schemas are proposals, not claims of Credential deployment."""
import copy
import json
from pathlib import Path
import unittest
from scripts.validate_http_contracts import validate,check_catalog

ROOT=Path(__file__).resolve().parents[1]

class DossierContractTests(unittest.TestCase):
 def setUp(self):
  self.catalog=json.loads((ROOT/'contracts/http/service-operations.json').read_text())
  self.protocol=json.loads((ROOT/'contracts/dossier/v1.json').read_text())
 def test_only_coordinator_can_drive_the_three_real_participants(self):
  operations=[o for o in self.catalog['operations'] if '.dossier.' in o['name']]
  self.assertEqual(len(operations),24)
  self.assertEqual(self.protocol['version'],1)
  self.assertEqual(set(self.protocol['participants']),{'credential-service','applicant-service','university-record-service'})
  self.assertFalse(self.catalog['coordinators']['message-broker']['externalCallerCredential'])
  for op in operations:
   self.assertEqual(op['callers'],['message-broker'])
   self.assertEqual(op['method'],'POST')
   if op['owner']=='credential-service':self.assertEqual(op['status'],'candidate')
   else:self.assertEqual(op['status'],'implemented-pending-review')
 def test_prepare_requires_real_fact_version_and_correlated_workflow_identity(self):
  example=json.loads((ROOT/'contracts/http/examples/applicant.dossier.prepare.json').read_text())
  body=example['request']['body'];schemas=self.catalog['schemas']
  self.assertEqual(validate(body,schemas['dossierPrepareV1'],schemas),[])
  for transform in (lambda b:b['identity'].update(version=True),lambda b:b['identity'].update(version=2),lambda b:b.update(sourceVersion='initialization-envelope-hash'),lambda b:b.update(credentialIds=[]),lambda b:b.update(credentialIds=b['credentialIds']*2)):
   invalid=copy.deepcopy(body);transform(invalid)
   self.assertTrue(validate(invalid,schemas['dossierPrepareV1'],schemas))
  self.assertTrue(validate({'late':'callback'},schemas['dossierEmptyV1'],schemas))
 def test_coordinator_declaration_cannot_authorize_an_external_identity(self):
  invalid=copy.deepcopy(self.catalog)
  invalid['coordinators']['message-broker']['externalCallerCredential']=True
  self.assertTrue(check_catalog(invalid))
  schemas=self.catalog['schemas']
  reply=json.loads((ROOT/'contracts/http/examples/credential.dossier.snapshot.json').read_text())['response']['body']
  self.assertEqual(validate(reply,schemas['dossierCredentialSnapshotV1'],schemas),[])
  reply['facts']['generationPath']='LEGACY'
  self.assertTrue(validate(reply,schemas['dossierCredentialSnapshotV1'],schemas))
