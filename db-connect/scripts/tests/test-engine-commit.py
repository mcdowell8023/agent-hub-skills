#!/usr/bin/env python3
"""
test-engine-commit.py —— db_engine.py 的写入提交语义。

缘起（2026-08-13）：ACS 线要执行一份迁移 SQL，发现 `db query` 的 DML
**静默回滚且退出码 0** —— 语句执行了、事务没提交、连接一关全丢，调用方看到
空结果 + exit 0，会以为写成功了。这比「不支持写」危险得多。

根因：`mysql_query_rows` 在 `finally` 里只 `conn.close()`，而 pymysql 默认
`autocommit=False` ⇒ 未提交的事务在关连接时回滚。全文件 `commit`/`autocommit` 零出现。

⛔ 既有的 29 条 bash 测试把整个引擎 mock 掉了（测的是 db.sh 的守卫），
   所以这个缺陷在测试里完全不可见 —— 本文件补的就是这一层。

⚠️ 安全边界不由本层负责，且**不得被本次改动放宽**：
   - DDL 永远禁止 —— `db.sh:149 MYSQL_DENY_REGEX`
   - readonly 禁 INSERT/UPDATE/DELETE/REPLACE —— `db.sh:174-176`
   这两道在 db.sh，进不到引擎。引擎只负责「放行进来的写，要么真写、要么报错」。
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db_engine  # noqa: E402


class FakeCursor:
    def __init__(self, description=None, rowcount=0, rows=()):
        self.description = description
        self.rowcount = rowcount
        self._rows = rows
        self.executed = []

    def execute(self, sql):
        self.executed.append(sql)

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = 0
        self.rolled_back = 0
        self.closed = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        self.closed += 1


class WriteCommitTest(unittest.TestCase):
    def _run(self, sql, description=None, rowcount=0, rows=()):
        cur = FakeCursor(description=description, rowcount=rowcount, rows=rows)
        conn = FakeConn(cur)
        with mock.patch.object(db_engine, "mysql_connect", return_value=conn):
            result = db_engine.mysql_query_rows({}, sql)
        return conn, cur, result

    # ── 写语句必须提交 ────────────────────────────────────────────────
    def test_insert_commits(self):
        conn, _, _ = self._run("INSERT INTO t (a) VALUES (1)", rowcount=1)
        self.assertEqual(conn.committed, 1, "INSERT 必须 commit，否则关连接即回滚")

    def test_update_commits(self):
        conn, _, _ = self._run("UPDATE t SET a=1 WHERE id=2", rowcount=3)
        self.assertEqual(conn.committed, 1)

    def test_delete_commits(self):
        conn, _, _ = self._run("DELETE FROM t WHERE id=2", rowcount=1)
        self.assertEqual(conn.committed, 1)

    def test_replace_commits(self):
        conn, _, _ = self._run("REPLACE INTO t (a) VALUES (1)", rowcount=1)
        self.assertEqual(conn.committed, 1)

    # ── 影响行数必须可见（否则调用方仍分不清成功与否）────────────────
    def test_affected_rows_reported(self):
        # 带 WHERE —— 本用例验的是「影响行数要回传」，不是无 WHERE 能不能跑
        # （无 WHERE 由 NoWhereGuardTest 单独拦，见下）
        _, _, (columns, rows) = self._run("UPDATE t SET a=1 WHERE id>0", rowcount=7)
        flat = " ".join(columns) + " " + " ".join(str(v) for r in rows for v in r)
        self.assertIn("7", flat, "必须把影响行数返回给调用方，⛔ 不能只回空结果")

    # ── 读语句不受影响（行为等价，这是本次改动的判据）────────────────
    def test_select_unchanged(self):
        conn, _, (columns, rows) = self._run(
            "SELECT id FROM t",
            description=[("id",)],
            rows=[(1,), (2,)],
        )
        self.assertEqual(columns, ["id"])
        self.assertEqual(rows, [["1"], ["2"]])
        self.assertEqual(conn.committed, 0, "只读语句不该 commit")

    def test_show_unchanged(self):
        _, _, (columns, rows) = self._run(
            "SHOW TABLES", description=[("Tables_in_db",)], rows=[("t",)]
        )
        self.assertEqual(columns, ["Tables_in_db"])
        self.assertEqual(rows, [["t"]])

    # ── 失败必须炸，⛔ 不许静默 ──────────────────────────────────────
    def test_commit_failure_raises(self):
        cur = FakeCursor(rowcount=1)
        conn = FakeConn(cur)
        conn.commit = mock.Mock(side_effect=RuntimeError("commit failed"))
        with mock.patch.object(db_engine, "mysql_connect", return_value=conn):
            with self.assertRaises(BaseException):
                db_engine.mysql_query_rows({}, "INSERT INTO t (a) VALUES (1)")

    # ── 连接始终关闭（别因为加了 commit 就漏掉 close）──────────────────
    def test_connection_always_closed(self):
        conn, _, _ = self._run("INSERT INTO t (a) VALUES (1)", rowcount=1)
        self.assertEqual(conn.closed, 1)




class NoWhereGuardTest(unittest.TestCase):
    """
    无 WHERE 的 UPDATE/DELETE 一律拒绝（用户 2026-08-13 拍板）。

    为什么放在引擎而不是 db.sh：db.sh 的守卫管的是**权限**
    （readonly / DDL，见 db.sh:149,174），这条管的是**影响面**——
    全表覆盖在任何环境都不该由 agent 随手执行，与连接是 full 还是 readonly 无关。
    而引擎是真正执行 commit 的那一层，守在这里离后果最近。

    ⚠️ 这道门在「写会静默回滚」的年代形同虚设（写了也不落），
       commit 修好后才真正有牙 —— 变的不是能不能写，是写错的代价。
    """

    def _run(self, sql, rowcount=1):
        cur = FakeCursor(rowcount=rowcount)
        conn = FakeConn(cur)
        with mock.patch.object(db_engine, "mysql_connect", return_value=conn):
            return db_engine.mysql_query_rows({}, sql), conn

    def _assert_blocked(self, sql):
        cur = FakeCursor(rowcount=1)
        conn = FakeConn(cur)
        with mock.patch.object(db_engine, "mysql_connect", return_value=conn):
            with self.assertRaises(BaseException, msg=f"应被拒绝: {sql}"):
                db_engine.mysql_query_rows({}, sql)
        self.assertEqual(cur.executed, [], f"⛔ 拒绝必须发生在 execute 之前: {sql}")
        self.assertEqual(conn.committed, 0)

    # ── 必须拒 ────────────────────────────────────────────────────────
    def test_update_without_where_blocked(self):
        self._assert_blocked("UPDATE users SET status='x'")

    def test_delete_without_where_blocked(self):
        self._assert_blocked("DELETE FROM users")

    def test_case_insensitive(self):
        self._assert_blocked("update users set a=1")
        self._assert_blocked("Delete From users")

    def test_leading_whitespace_and_newlines(self):
        self._assert_blocked("\n   UPDATE users\n   SET a=1\n")

    def test_where_only_in_line_comment_blocked(self):
        """⛔ 注释里的 WHERE 不算 —— 否则 `DELETE FROM t -- WHERE x` 就绕过去了。"""
        self._assert_blocked("DELETE FROM users -- WHERE id=1")
        self._assert_blocked("DELETE FROM users # WHERE id=1")

    def test_where_only_in_block_comment_blocked(self):
        self._assert_blocked("UPDATE users SET a=1 /* WHERE id=1 */")

    # ── 不能误伤 ──────────────────────────────────────────────────────
    def test_update_with_where_allowed(self):
        (_, _), conn = self._run("UPDATE users SET a=1 WHERE id=2")
        self.assertEqual(conn.committed, 1)

    def test_delete_with_where_allowed(self):
        (_, _), conn = self._run("DELETE FROM users WHERE id=2")
        self.assertEqual(conn.committed, 1)

    def test_insert_not_affected(self):
        """INSERT 本来就没有 WHERE，⛔ 不能被这道门误伤。"""
        (_, _), conn = self._run("INSERT INTO users (a) VALUES (1)")
        self.assertEqual(conn.committed, 1)

    def test_replace_not_affected(self):
        (_, _), conn = self._run("REPLACE INTO users (a) VALUES (1)")
        self.assertEqual(conn.committed, 1)

    def test_select_not_affected(self):
        cur = FakeCursor(description=[("id",)], rows=[(1,)])
        conn = FakeConn(cur)
        with mock.patch.object(db_engine, "mysql_connect", return_value=conn):
            columns, rows = db_engine.mysql_query_rows({}, "SELECT id FROM users")
        self.assertEqual(columns, ["id"])

    def test_where_lowercase_allowed(self):
        (_, _), conn = self._run("update users set a=1 where id=2")
        self.assertEqual(conn.committed, 1)

    def test_update_with_where_and_comment_allowed(self):
        """注释里有没有 WHERE 无所谓，语句本体有就行。"""
        (_, _), conn = self._run("UPDATE users SET a=1 /* 批注 */ WHERE id=2")
        self.assertEqual(conn.committed, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
