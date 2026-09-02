import unittest

from security_guard import check_sql_safety


class SecurityGuardTest(unittest.TestCase):
    def assert_rejected(self, sql):
        safe, error = check_sql_safety(sql)
        self.assertFalse(safe, msg=f"SQL should be rejected: {sql}")
        self.assertTrue(error)

    def test_allows_select(self):
        safe, error = check_sql_safety(
            "SELECT COUNT(*) FROM ads_cust_info_d WHERE data_dt = '20260531'"
        )
        self.assertTrue(safe, msg=error)

    def test_allows_select_with_cte(self):
        safe, error = check_sql_safety(
            "WITH customers AS ("
            "SELECT pty_id FROM ads_cust_info_d WHERE data_dt = '20260531'"
            ") SELECT COUNT(*) FROM customers"
        )
        self.assertTrue(safe, msg=error)

    def test_rejects_write_statements(self):
        cases = [
            "INSERT INTO ads_cust_info_d (pty_id) VALUES ('1')",
            "UPDATE ads_cust_info_d SET pty_id = '1'",
            "DELETE FROM ads_cust_info_d",
            "DROP TABLE ads_cust_info_d",
        ]
        for sql in cases:
            with self.subTest(sql=sql):
                self.assert_rejected(sql)

    def test_rejects_multiple_statements(self):
        self.assert_rejected("SELECT 1; DROP TABLE ads_cust_info_d")

    def test_rejects_data_modifying_cte(self):
        self.assert_rejected(
            "WITH removed AS ("
            "DELETE FROM ads_cust_info_d RETURNING pty_id"
            ") SELECT * FROM removed"
        )

    def test_rejects_unknown_table(self):
        self.assert_rejected("SELECT * FROM non_exist_table")

    def test_allows_derived_table_column(self):
        sql = (
            "SELECT SUM(x.tran_amt) FROM ("
            "SELECT t.pty_id, SUM(t.buy_amt) AS tran_amt "
            "FROM dwd_cust_tran_d t GROUP BY t.pty_id"
            ") x"
        )
        safe, error = check_sql_safety(sql)
        self.assertTrue(safe, msg=error)

    def test_rejects_invalid_inner_table_column(self):
        sql = (
            "SELECT SUM(x.tran_amt) FROM ("
            "SELECT t.pty_id, SUM(t.not_a_column) AS tran_amt "
            "FROM dwd_cust_tran_d t GROUP BY t.pty_id"
            ") x"
        )
        self.assert_rejected(sql)


if __name__ == '__main__':
    unittest.main()
