import json,tempfile,unittest
from pathlib import Path
from dft_contracts.project import document_path
from dft_contracts.paired import _rules
class StageReports(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
  (self.root/'dft-project.json').write_text(json.dumps({'schema_version':1,'storage_role':'cluster','routes':[{'path':'sample/bands','composition':'si','structure':'bulk'}]}))
  self.stage=self.root/'sample/bands/01_tests';self.leaf=self.stage/'k8';self.leaf.mkdir(parents=True)
 def tearDown(self):self.tmp.cleanup()
 def test_stage_and_variant_share_report(self):
  for scope in [self.stage,self.leaf]:self.assertEqual(document_path(self.root,'report','convergence','.md',scope),self.stage/'README.md')
 def test_no_cluster_plan_or_main_report(self):
  for kind in ['plan','log','main_report','note']:
   with self.assertRaises(ValueError):document_path(self.root,kind,'convergence','.md',self.stage)
 def test_report_requires_stage_and_markdown(self):
  for scope,ext in [(self.root/'.', '.md'),(self.stage,'.json')]:
   with self.assertRaises(ValueError):document_path(self.root,'report','convergence',ext,scope)
 def test_generated_instructions(self):
  self.assertIn('Numbered-stage README owns stage analysis',_rules('cluster'))
  self.assertNotIn('facts only',_rules('cluster'))
if __name__=='__main__':unittest.main()
