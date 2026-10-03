"""Transactional transfer API + atomic outbox, using integer cents and SQLite."""
import argparse, json, sqlite3, tempfile, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

class Conflict(ValueError): pass
class Store:
    def __init__(self,path):
        self.db=sqlite3.connect(path,isolation_level=None,timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript("""CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,balance INTEGER NOT NULL CHECK(balance>=0));
        CREATE TABLE IF NOT EXISTS transfers(key TEXT PRIMARY KEY,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY,transfer_key TEXT UNIQUE NOT NULL,state TEXT NOT NULL CHECK(state IN ('PENDING','RUNNING','DONE','HOLD')),owner TEXT);
        CREATE TABLE IF NOT EXISTS deliveries(job_id INTEGER PRIMARY KEY,body TEXT NOT NULL);""")
    def close(self): self.db.close()
    def seed(self):
        self.db.executemany('INSERT OR IGNORE INTO accounts VALUES(?,?)',[('alice',100000),('bob',0)])
    def balances(self): return dict(self.db.execute('SELECT id,balance FROM accounts ORDER BY id'))
    def transfer(self,key,source,target,cents,fail=None):
        if not isinstance(key,str) or not 1<=len(key)<=128 or type(cents) is not int or not 0<cents<=10**12 or not isinstance(source,str) or not isinstance(target,str) or source==target:
            raise ValueError('INVALID_TRANSFER')
        payload=json.dumps([source,target,cents],separators=(',',':'))
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old=self.db.execute('SELECT payload FROM transfers WHERE key=?',(key,)).fetchone()
            if old:
                if old[0]!=payload: raise Conflict('KEY_PAYLOAD_CONFLICT')
                self.db.execute('COMMIT'); return {'key':key,'replayed':True}
            if self.db.execute('SELECT 1 FROM accounts WHERE id=?',(target,)).fetchone() is None: raise ValueError('TARGET_UNKNOWN')
            if self.db.execute('UPDATE accounts SET balance=balance-? WHERE id=? AND balance>=?',(cents,source,cents)).rowcount!=1: raise Conflict('INSUFFICIENT_FUNDS_OR_SOURCE_UNKNOWN')
            if fail=='after_debit': raise RuntimeError('INJECTED_FAILURE')
            self.db.execute('UPDATE accounts SET balance=balance+? WHERE id=?',(cents,target))
            self.db.execute('INSERT INTO transfers VALUES(?,?)',(key,payload))
            self.db.execute("INSERT INTO jobs(transfer_key,state) VALUES(?,'PENDING')",(key,))
            self.db.execute('COMMIT'); return {'key':key,'replayed':False}
        except BaseException:
            self.db.execute('ROLLBACK');raise
    def claim(self,owner):
        if not isinstance(owner,str) or not owner: raise ValueError('OWNER_REQUIRED')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute("SELECT id FROM jobs WHERE state='PENDING' ORDER BY id LIMIT 1").fetchone()
            if row: self.db.execute("UPDATE jobs SET state='RUNNING',owner=? WHERE id=?",(owner,row[0]))
            self.db.execute('COMMIT');return row[0] if row else None
        except BaseException: self.db.execute('ROLLBACK');raise
    def finish(self,job,owner,fail=False):
        # The demo sink shares the transaction. External effects require a different protocol.
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute("SELECT transfer_key FROM jobs WHERE id=? AND state='RUNNING' AND owner=?",(job,owner)).fetchone()
            if row is None: raise Conflict('NOT_JOB_OWNER')
            self.db.execute('INSERT INTO deliveries VALUES(?,?)',(job,row[0]))
            if fail: raise RuntimeError('INJECTED_FAILURE')
            self.db.execute("UPDATE jobs SET state='DONE' WHERE id=?",(job,))
            self.db.execute('COMMIT')
        except BaseException: self.db.execute('ROLLBACK');raise
    def recover_stopped_worker(self,owner):
        # Operator must first stop the named worker. Never silently replay an external effect.
        return self.db.execute("UPDATE jobs SET state='HOLD' WHERE state='RUNNING' AND owner=?",(owner,)).rowcount

def server(path,port=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def respond(self,status,body):
            data=json.dumps(body).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_GET(self):
            if self.path!='/balances': return self.respond(404,{'error':'NOT_FOUND'})
            s=Store(path)
            try:self.respond(200,s.balances())
            finally:s.close()
        def do_POST(self):
            if self.path!='/transfers': return self.respond(404,{'error':'NOT_FOUND'})
            s=None
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4096: raise ValueError('BODY_SIZE')
                body=json.loads(self.rfile.read(size))
                if not isinstance(body,dict) or set(body)!={'source','target','cents'}: raise ValueError('BODY_SCHEMA')
                s=Store(path);result=s.transfer(self.headers.get('Idempotency-Key'),**body);self.respond(200 if result['replayed'] else 201,result)
            except Conflict as e:self.respond(409,{'error':str(e)})
            except (ValueError,TypeError) as e:self.respond(400,{'error':str(e)})
            finally:
                if s:s.close()
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)

def benchmark(n=200):
    with tempfile.TemporaryDirectory() as tmp:
        s=Store(Path(tmp)/'b.sqlite');s.seed();start=time.perf_counter()
        for i in range(n):s.transfer(str(i),'alice','bob',1)
        elapsed=time.perf_counter()-start;balances=s.balances();s.close()
        return {'operations':n,'seconds':elapsed,'operations_per_second':n/elapsed,'balances':balances,'scope':'single local SQLite writer; not production throughput'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['demo','benchmark','serve'],default='demo',nargs='?');p.add_argument('--db',default='lab.sqlite');p.add_argument('--port',type=int,default=8080);a=p.parse_args()
    if a.mode=='serve':
        s=Store(a.db);s.seed();s.close();server(a.db,a.port).serve_forever()
    elif a.mode=='benchmark':print(json.dumps(benchmark(),indent=2))
    else:
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(Path(tmp)/'demo.sqlite');s.seed();first=s.transfer('invoice-1','alice','bob',2500);replay=s.transfer('invoice-1','alice','bob',2500);j=s.claim('local');s.finish(j,'local');print(json.dumps({'first':first,'replay':replay,'balances':s.balances(),'job':'DONE'},indent=2));s.close()
