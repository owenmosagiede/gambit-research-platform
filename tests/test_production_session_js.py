import json
from pathlib import Path
import subprocess
import unittest

class SessionBridgeTests(unittest.TestCase):
    def test_csrf_is_same_origin_and_expiration_never_resends(self):
        path=Path(__file__).resolve().parents[1]/'src/web/session.js'
        code='''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
let calls=[],notices=0,status=200;
const document={querySelector:s=>s.startsWith('meta')?{content:'fixture-csrf'}:null,
  createElement:()=>({setAttribute(){},append(){}}),body:{prepend(){notices++;}}};
const window={location:{href:'https://gambitsystems.xyz/app/',origin:'https://gambitsystems.xyz'},
  fetch:async(input,options)=>{calls.push({input,options});return{status};}};
vm.runInNewContext(fs.readFileSync(PATH,'utf8'),{window,document,URL,Headers});
(async()=>{
 await window.fetch('/api/experiments');assert.equal(calls[0].options.headers.has('X-CSRFToken'),false);
 const frozen=JSON.stringify({request_id:'same-frozen-id'});
 await window.fetch('/api/experiments',{method:'POST',body:frozen});
 assert.equal(calls[1].options.headers.get('X-CSRFToken'),'fixture-csrf');
 assert.equal(calls[1].options.body,frozen);
 await window.fetch('https://elsewhere.example/api/test',{method:'POST'});
 assert.equal(calls[2].options.headers,undefined);
 status=401;await window.fetch('/api/experiments');await window.fetch('/api/experiments');
 assert.equal(notices,1);assert.equal(calls.length,5);
 assert.equal(calls.filter(c=>c.options.method==='POST'&&c.input==='/api/experiments').length,1);
 console.log('Session bridge passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''.replace('PATH',json.dumps(str(path)))
        result=subprocess.run(['node','-e',code],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
