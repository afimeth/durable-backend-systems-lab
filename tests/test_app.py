import concurrent.futures,json,sqlite3,subprocess,sys,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from app import Store,Conflict,server,benchmark
class Tests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.sqlite';self.s=Store(self.path);self.s.seed()
    def tearDown(self):self.s.close();self.tmp.cleanup()
    def test_transfer_conserves_money(self):self.s.transfer('a','alice','bob',123);self.assertEqual(self.s.balances(),{'alice':99877,'bob':123})
    def test_replay_returns_previous(self):self.s.transfer('a','alice','bob',123);self.assertTrue(self.s.transfer('a','alice','bob',123)['replayed']);self.assertEqual(self.s.balances()['bob'],123)
    def test_key_conflict(self):
        self.s.transfer('a','alice','bob',1)
        with self.assertRaises(Conflict):self.s.transfer('a','alice','bob',2)
    def test_rollback_has_no_partial_debit_or_job(self):
        with self.assertRaises(RuntimeError):self.s.transfer('a','alice','bob',1,'after_debit')
        self.assertEqual(self.s.balances()['alice'],100000);self.assertEqual(self.s.db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
    def test_insufficient_funds(self):
        with self.assertRaises(Conflict):self.s.transfer('a','alice','bob',100001)
        self.assertEqual(self.s.balances()['alice'],100000)
    def test_input_bounds(self):
        for n in (0,-1,True,1.5,10**13):
            with self.assertRaises(ValueError):self.s.transfer('a','alice','bob',n)
    def test_unknown_target(self):
        with self.assertRaises(ValueError):self.s.transfer('a','alice','unknown',1)
    def test_two_connections_same_key(self):
        def run(_):
            s=Store(self.path)
            try:return s.transfer('race','alice','bob',50)['replayed']
            finally:s.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(run,range(16)))
        self.assertEqual(results.count(False),1);self.assertEqual(self.s.balances()['bob'],50)
    def test_concurrent_overdraft(self):
        def run(i):
            s=Store(self.path)
            try:s.transfer(str(i),'alice','bob',60000);return True
            except Conflict:return False
            finally:s.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
        self.assertEqual(sum(results),1);self.assertEqual(sum(self.s.balances().values()),100000)
    def test_job_owner_and_sink_transaction(self):
        self.s.transfer('a','alice','bob',1);j=self.s.claim('worker')
        with self.assertRaises(Conflict):self.s.finish(j,'stranger')
        with self.assertRaises(RuntimeError):self.s.finish(j,'worker',True)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM deliveries').fetchone()[0],0)
        self.s.finish(j,'worker');self.assertEqual(self.s.db.execute('SELECT state FROM jobs').fetchone()[0],'DONE')
    def test_recovery_is_hold_not_retry(self):
        self.s.transfer('a','alice','bob',1);self.s.claim('dead');self.s.close();self.s=Store(self.path)
        self.assertEqual(self.s.recover_stopped_worker('other'),0);self.assertEqual(self.s.recover_stopped_worker('dead'),1);self.assertIsNone(self.s.claim('new'))
    def test_claim_concurrency(self):
        self.s.transfer('a','alice','bob',1)
        def run(i):
            s=Store(self.path)
            try:return s.claim(str(i))
            finally:s.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:r=list(pool.map(run,range(4)))
        self.assertEqual(sum(x is not None for x in r),1)
    def test_process_killed_inside_transaction_rolls_back(self):
        code="import sqlite3,os,sys; d=sqlite3.connect(sys.argv[1]); d.execute('BEGIN IMMEDIATE'); d.execute(\"UPDATE accounts SET balance=0 WHERE id='alice'\"); os._exit(23)"
        p=subprocess.run([sys.executable,'-c',code,str(self.path)]);self.assertEqual(p.returncode,23);self.assertEqual(self.s.balances()['alice'],100000)
    def test_process_restart_keeps_commit(self):
        self.s.transfer('a','alice','bob',42);self.s.close();self.s=Store(self.path);self.assertTrue(self.s.transfer('a','alice','bob',42)['replayed'])
    def test_http_contract(self):
        srv=server(self.path);t=threading.Thread(target=srv.serve_forever,daemon=True);t.start();url=f'http://127.0.0.1:{srv.server_port}'
        try:
            def post(cents):return urllib.request.urlopen(urllib.request.Request(url+'/transfers',json.dumps({'source':'alice','target':'bob','cents':cents}).encode(),{'Idempotency-Key':'http','Content-Type':'application/json'}),timeout=5)
            with post(5) as r:self.assertEqual(r.status,201)
            with post(5) as r:self.assertEqual(r.status,200)
            with self.assertRaises(urllib.error.HTTPError) as e:post(6)
            self.assertEqual(e.exception.code,409)
            e.exception.close()
            with urllib.request.urlopen(url+'/balances',timeout=5) as r:self.assertEqual(json.load(r)['bob'],5)
        finally:srv.shutdown();srv.server_close();t.join()
    def test_benchmark_correctness(self):self.assertEqual(benchmark(20)['balances']['bob'],20)
