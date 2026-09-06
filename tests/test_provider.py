"""Exercise actual SDK HTTP serialization against a local fake provider, never a billed API."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import json
from disaster.knowledge import provider_json


def test_compatible_provider_wire_format(monkeypatch):
    observed=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            observed.append((self.path,payload))
            body=json.dumps({'id':'local-test','object':'chat.completion','created':0,'model':'test-model',
                             'choices':[{'index':0,'message':{'role':'assistant','content':'{"ok": true}'},'finish_reason':'stop'}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self,*args):
            pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True)
    thread.start()
    monkeypatch.setenv('DISASTER_API_KEY','local-fake-test-key')
    monkeypatch.setenv('DISASTER_BASE_URL',f'http://127.0.0.1:{server.server_port}/v1')
    monkeypatch.setenv('DISASTER_MODEL','test-model')
    monkeypatch.setenv('NO_PROXY','127.0.0.1,localhost')
    monkeypatch.setenv('no_proxy','127.0.0.1,localhost')
    try:
        assert provider_json('return JSON',{'sample':'示例'})=={'ok':True}
        path,payload=observed[0]
        assert path=='/v1/chat/completions'
        assert payload['response_format']=={'type':'json_object'}
        assert payload['model']=='test-model'
        assert len(payload['messages'])==2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
