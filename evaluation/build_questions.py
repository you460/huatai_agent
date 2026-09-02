# -*- coding: utf-8 -*-
"""
生成 evaluation/test_questions.json（150 题：简单50 / 中等50 / 较难50）。

结构：
- 官方原题 7 道（中等3 + 较难4），SQL 原样取自 Q&A.xlsx，source='official'
- 其余为精简保留的旧题 + 官方风格新题，source='self'

数据关键事实（已跑库验证）：
- 省份名是「北京市/上海市/江苏省/广东省/浙江省/安徽省/四川省/云南省」（无「北京/上海」）
- 2026 Q1 = 90 天（日均除数 = 90）
- 消歧股票 A股 各1只：比亚迪/招商银行/中国平安/贵州茅台（万科A 为 0 只）
- 学历：博士6000002/硕士6000003/学士6000004/大专6000005/中专6000006/高中6000007/初中及以下6000008
- 客户等级：钻石1000001/白金1000002/金卡1000003/银卡1000004/普通(紫金理财卡)1000005/空1000006
- 性别：男5000002/女5000003；账户状态：正常2000001/销户2000004
"""
import json
import os

Q = []  # 每个元素: (difficulty, question, standard_sql, source)

def add(d, question, sql, source='self', **review_fields):
    Q.append({
        "difficulty": d,
        "question": question,
        "standard_sql": sql,
        "source": source,
        **review_fields,
    })


# ============================================================
# 简单（50 题）：单条件/双条件计数、单表求和聚合（无官方原题）
# ============================================================

add("简单", "客户信息表中总共有多少位客户",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531'")
add("简单", "男性客户有多少个",
    "select count(*) as male_cnt from ads_cust_info_d where data_dt='20260531' and gender_cd='5000002'")
add("简单", "女性客户有多少个",
    "select count(*) as female_cnt from ads_cust_info_d where data_dt='20260531' and gender_cd='5000003'")
add("简单", "钻石卡客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and cust_lvl_cd='1000001'")
add("简单", "白金卡客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and cust_lvl_cd='1000002'")
add("简单", "金卡客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and cust_lvl_cd='1000003'")
add("简单", "银卡客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and cust_lvl_cd='1000004'")
add("简单", "年龄大于70岁的客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and cust_age>70")
add("简单", "年龄小于30岁的客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and cust_age<30")
add("简单", "年龄在30岁到40岁之间的客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and cust_age between 30 and 40")
add("简单", "省份为北京市的客户有多少个",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and prov_name='北京市'")
add("简单", "省份为上海市的客户有多少个",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and prov_name='上海市'")
add("简单", "江苏省的客户有多少个",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and prov_name='江苏省'")
add("简单", "广东省的客户有多少个",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and prov_name='广东省'")
add("简单", "学历为硕士的客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and edu_cd='6000003'")
add("简单", "学历为学士的客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and edu_cd='6000004'")
add("简单", "学历为大专的客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and edu_cd='6000005'")
add("简单", "账户状态为正常的客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and cust_status='2000001'")
add("简单", "账户状态为销户的客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and cust_status='2000004'")
add("简单", "产品二级分类为A股的产品有多少只",
    "select count(*) as prdt_cnt from dim_product where prdt_type_name='A股'")
add("简单", "2026年3月31日所有客户普通账户总资产合计是多少",
    "select coalesce(sum(nm_tot_aset),0) as tot_aset from dws_cust_aset_d where data_dt='20260331'")
add("简单", "2026年3月31日信用账户净资产合计是多少",
    "select coalesce(sum(fc_pur_aset),0) as tot_fc_aset from dws_cust_aset_d where data_dt='20260331'")
add("简单", "2026年3月31日普通账户现金资产合计是多少",
    "select coalesce(sum(nm_bal),0) as tot_nm_bal from dws_cust_aset_d where data_dt='20260331'")
add("简单", "2026年3月31日信用账户现金资产合计是多少",
    "select coalesce(sum(fc_bal),0) as tot_fc_bal from dws_cust_aset_d where data_dt='20260331'")
add("简单", "2026年3月31日全市场客户持仓总市值是多少",
    "select coalesce(sum(mkt_val),0) as tot_mkt_val from dwd_cust_hold_d where data_dt='20260331'")
add("简单", "2026年第一季度全市场客户总买入金额是多少",
    "select coalesce(sum(buy_amt),0) as tot_buy_amt from dwd_cust_tran_d where data_dt between '20260101' and '20260331'")
add("简单", "2026年第一季度全市场客户总卖出金额是多少",
    "select coalesce(sum(sell_amt),0) as tot_sell_amt from dwd_cust_tran_d where data_dt between '20260101' and '20260331'")
add("简单", "2026年第一季度全市场客户总交易金额是多少",
    "select sum(coalesce(buy_amt,0)+coalesce(sell_amt,0)) as tot_tran_amt from dwd_cust_tran_d where data_dt between '20260101' and '20260331'")
add("简单", "客户平均年龄是多少",
    "select round(avg(cust_age),2) as avg_age from ads_cust_info_d where data_dt='20260531'")
add("简单", "男性客户的平均年龄是多少",
    "select round(avg(cust_age),2) as avg_age from ads_cust_info_d where data_dt='20260531' and gender_cd='5000002'")
add("简单", "女性客户的平均年龄是多少",
    "select round(avg(cust_age),2) as avg_age from ads_cust_info_d where data_dt='20260531' and gender_cd='5000003'")
add("简单", "客户中最大年龄是多少",
    "select max(cust_age) as max_age from ads_cust_info_d where data_dt='20260531'")
add("简单", "60岁以上的女性客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and gender_cd='5000003' and cust_age>=60")
add("简单", "男性钻石卡客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and gender_cd='5000002' and cust_lvl_cd='1000001'")
add("简单", "本科及以上学历的客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and edu_cd in ('6000002','6000003','6000004')")
add("简单", "硕士及以上学历的客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and edu_cd in ('6000002','6000003')")
add("简单", "年龄在50岁以上的男性客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and cust_age>=50 and gender_cd='5000002'")
add("简单", "年龄在60岁以上的钻石卡客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and cust_age>=60 and cust_lvl_cd='1000001'")
add("简单", "北京市且年龄大于50岁的客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and prov_name='北京市' and cust_age>50")
add("简单", "上海市的男性客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and prov_name='上海市' and gender_cd='5000002'")
add("简单", "学历为硕士的男性客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and edu_cd='6000003' and gender_cd='5000002'")
add("简单", "年龄小于30岁的女性客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and cust_age<30 and gender_cd='5000003'")
add("简单", "银卡且年龄大于50岁的客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and cust_lvl_cd='1000004' and cust_age>50")
add("简单", "江苏省的男性客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and prov_name='江苏省' and gender_cd='5000002'")
add("简单", "2026年3月31日普通账户现金资产大于10万元的客户数量",
    "select count(*) as cust_cnt from dws_cust_aset_d where data_dt='20260331' and nm_bal>100000")
add("简单", "2026年3月31日普通账户现金资产大于5万元的客户数量",
    "select count(*) as cust_cnt from dws_cust_aset_d where data_dt='20260331' and nm_bal>50000")
add("简单", "2026年3月31日总资产大于100万元的客户数量",
    "select count(*) as cust_cnt from dws_cust_aset_d where data_dt='20260331' and (coalesce(nm_tot_aset,0)+coalesce(fc_pur_aset,0))>1000000")
add("简单", "2026年3月31日总资产大于500万元的客户数量",
    "select count(*) as cust_cnt from dws_cust_aset_d where data_dt='20260331' and (coalesce(nm_tot_aset,0)+coalesce(fc_pur_aset,0))>5000000")
add("简单", "本科及以上学历的男性客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and edu_cd in ('6000002','6000003','6000004') and gender_cd='5000002'")
add("简单", "年龄大于60岁的男性客户有多少位",
    "select count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and cust_age>60 and gender_cd='5000002'")


# ============================================================
# 中等（50 题）：官方3 + 旧题20 + 新题27
# ============================================================

# ---- 官方原题 3 道 ----
add("中等", "学历本科及以上的男性客户，年龄大于50岁的有多少个",
    """select count(*)
from ads_cust_info_d a
left join dim_public b on a.edu_cd = b.code and b.code_type_id='600'
left join dim_public c on a.gender_cd = c.code and c.code_type_id='500'
where b.describe in ('博士','硕士','学士') and c.describe in ('男')
and a.cust_age>50""", source='official',
    reviewed_standard_sql="""select count(*)
from ads_cust_info_d a
left join dim_public b on a.edu_cd = b.code and b.code_type_id='600'
left join dim_public c on a.gender_cd = c.code and c.code_type_id='500'
where a.data_dt='20260531'
and b.describe in ('博士','硕士','学士') and c.describe in ('男')
and a.cust_age>50""",
    review_status='approved',
    review_note='客户信息表按客户+日期存储，统计客户人数需限定最新快照日期。')

add("中等", "不同客户年龄段资产分布情况，如下规则：1、小于30；2、大于等于30，小于50；3、大于等于50，小于60；4、大于60",
    """select case when cust_age<30 then '<30'
     when cust_age>=30 and cust_age<50 then '[30,50)'
     when cust_age>=50 and cust_age<60 then '[50,60)'
     when cust_age>=60 then '[60,)'
    end as cust_age_type
  ,sum(coalesce(b.nm_tot_aset,0)+coalesce(b.fc_pur_aset,0)) as aset
from ads_cust_info_d a
left join dws_cust_aset_d b on a.pty_id=b.pty_id and b.data_dt='20260331'
where a.data_dt='20260531'
group by case when cust_age<30 then '<30'
     when cust_age>=30 and cust_age<50 then '[30,50)'
     when cust_age>=50 and cust_age<60 then '[50,60)'
     when cust_age>=60 then '[60,)'
    end""", source='official',
    reviewed_question="不同客户年龄段资产分布情况，如下规则：1、小于30；2、大于等于30，小于50；3、大于等于50，小于60；4、大于等于60",
    review_status='approved',
    review_note='使题干与标准 SQL 的 [60,) 分组保持一致。')

add("中等", "分公司各营业部的客户省份分析统计",
    """select b.up_org_name,b.org_name,a.prov_name,a.city_name,count(*) as cnt
from ads_cust_info_d a
inner join dim_branch b on a.org_id=b.org_id
group by b.up_org_name,b.org_name,a.prov_name,a.city_name""", source='official',
    reviewed_question='分公司各营业部的客户省份、城市分析统计',
    reviewed_standard_sql="""select b.up_org_name,b.org_name,a.prov_name,a.city_name,count(*) as cnt
from ads_cust_info_d a
inner join dim_branch b on a.org_id=b.org_id
where a.data_dt='20260531'
group by b.up_org_name,b.org_name,a.prov_name,a.city_name""",
    review_status='approved',
    review_note='避免同一客户多日快照重复计入分公司、营业部、省市统计。')

# ---- 旧题保留 20 道 ----
add("中等", "按省份统计客户数量，从多到少排序",
    "select prov_name, count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' group by prov_name order by cust_cnt desc")
add("中等", "统计不同性别的客户数量",
    "select b.describe as gender_name, count(*) as cust_cnt from ads_cust_info_d a left join dim_public b on a.gender_cd = b.code and b.code_type_id='500' where a.data_dt='20260531' group by b.describe")
add("中等", "统计各个客户等级的客户人数",
    "select b.describe as cust_lvl_name, count(*) as cust_cnt from ads_cust_info_d a left join dim_public b on a.cust_lvl_cd = b.code and b.code_type_id='100' where a.data_dt='20260531' group by b.describe order by cust_cnt desc")
add("中等", "2026年3月31日，每个产品的持仓总市值，按市值降序",
    "select b.prdt_name, sum(a.mkt_val) as tot_mkt_val from dwd_cust_hold_d a inner join dim_product b on a.prdt_id = b.prdt_id where a.data_dt='20260331' group by b.prdt_name order by tot_mkt_val desc")
add("中等", "统计每个营业部的客户数量",
    "select b.up_org_name, b.org_name, count(*) as cust_cnt from ads_cust_info_d a inner join dim_branch b on a.org_id = b.org_id where a.data_dt='20260531' group by b.up_org_name, b.org_name")
add("中等", "2026年3月31日，客户总资产排名前10的客户号和金额",
    "select pty_id, (coalesce(nm_tot_aset,0) + coalesce(fc_pur_aset,0)) as tot_aset from dws_cust_aset_d where data_dt='20260331' order by tot_aset desc limit 10")
add("中等", "按产品一级分类统计持仓总市值",
    "select b.up_prdt_type_name, sum(a.mkt_val) as tot_mkt_val from dwd_cust_hold_d a inner join dim_product b on a.prdt_id = b.prdt_id where a.data_dt='20260331' group by b.up_prdt_type_name")
add("中等", "2026年第一季度，每个客户的总交易金额",
    "select pty_id, sum(coalesce(buy_amt,0) + coalesce(sell_amt,0)) as tot_tran_amt from dwd_cust_tran_d where data_dt between '20260101' and '20260331' group by pty_id")
add("中等", "统计不同学历的客户平均年龄",
    "select b.describe as edu_name, avg(a.cust_age) as avg_age from ads_cust_info_d a left join dim_public b on a.edu_cd = b.code and b.code_type_id='600' where a.data_dt='20260531' group by b.describe")
add("中等", "2026年3月31日，普通账户和信用账户的总资产分别是多少",
    "select coalesce(sum(nm_tot_aset), 0) as nm_tot_aset, coalesce(sum(fc_pur_aset), 0) as fc_tot_aset from dws_cust_aset_d where data_dt='20260331'")
add("中等", "按城市统计客户数量，从多到少排序",
    "select city_name, count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' group by city_name order by cust_cnt desc")
add("中等", "统计不同职业的客户数量",
    "select b.describe as prof_name, count(*) as cust_cnt from ads_cust_info_d a left join dim_public b on a.prof_cd = b.code and b.code_type_id='700' where a.data_dt='20260531' group by b.describe order by cust_cnt desc")
add("中等", "2026年3月31日，按产品二级分类统计持仓总市值，前10名",
    "select b.prdt_type_name, sum(a.mkt_val) as tot_mkt_val from dwd_cust_hold_d a inner join dim_product b on a.prdt_id = b.prdt_id where a.data_dt='20260331' group by b.prdt_type_name order by tot_mkt_val desc limit 10")
add("中等", "统计每个分公司的营业部数量",
    "select up_org_name, count(distinct org_id) as branch_cnt from dim_branch group by up_org_name order by branch_cnt desc")
add("中等", "2026年Q1，每个产品的总交易金额，前10名",
    "select b.prdt_name, sum(coalesce(a.buy_amt,0)+coalesce(a.sell_amt,0)) as tot_tran_amt from dwd_cust_tran_d a inner join dim_product b on a.prdt_id = b.prdt_id where a.data_dt between '20260101' and '20260331' group by b.prdt_name order by tot_tran_amt desc limit 10")
add("中等", "统计不同账户状态的客户数量",
    "select b.describe as status_name, count(*) as cust_cnt from ads_cust_info_d a left join dim_public b on a.cust_status = b.code and b.code_type_id='200' where a.data_dt='20260531' group by b.describe")
add("中等", "2026年3月31日，各省份客户的平均总资产",
    "select a.prov_name, avg(coalesce(b.nm_tot_aset,0)+coalesce(b.fc_pur_aset,0)) as avg_tot_aset from ads_cust_info_d a left join dws_cust_aset_d b on a.pty_id = b.pty_id and b.data_dt='20260331' where a.data_dt='20260531' group by a.prov_name order by avg_tot_aset desc")
add("中等", "按客户等级统计平均年龄",
    "select b.describe as cust_lvl_name, avg(a.cust_age) as avg_age from ads_cust_info_d a left join dim_public b on a.cust_lvl_cd = b.code and b.code_type_id='100' where a.data_dt='20260531' group by b.describe")
add("中等", "2026年Q1，普通账户和信用账户的总交易金额分别是多少",
    "select sys_source, sum(coalesce(buy_amt,0)+coalesce(sell_amt,0)) as tot_tran_amt from dwd_cust_tran_d where data_dt between '20260101' and '20260331' group by sys_source")
add("中等", "统计持有A股产品的客户数量",
    "select count(distinct a.pty_id) as cust_cnt from dwd_cust_hold_d a inner join dim_product b on a.prdt_id = b.prdt_id where a.data_dt='20260331' and b.prdt_type_name='A股'")

# ---- 新题 27 道 ----
add("中等", "按年龄段统计客户数量",
    "select case when cust_age<30 then '<30' when cust_age>=30 and cust_age<50 then '[30,50)' when cust_age>=50 and cust_age<60 then '[50,60)' else '[60,)' end as age_type, count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' group by 1 order by 1")
add("中等", "按年龄段统计男性客户数量",
    "select case when cust_age<30 then '<30' when cust_age>=30 and cust_age<50 then '[30,50)' when cust_age>=50 and cust_age<60 then '[50,60)' else '[60,)' end as age_type, count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' and gender_cd='5000002' group by 1 order by 1")
add("中等", "按客户等级统计客户总资产合计",
    "select b.describe as cust_lvl, sum(coalesce(a.nm_tot_aset,0)+coalesce(a.fc_pur_aset,0)) as tot_aset from dws_cust_aset_d a join ads_cust_info_d c on a.pty_id=c.pty_id and c.data_dt='20260531' left join dim_public b on c.cust_lvl_cd=b.code and b.code_type_id='100' where a.data_dt='20260331' group by b.describe order by tot_aset desc")
add("中等", "各分公司客户数量排名",
    "select b.up_org_name, count(distinct a.pty_id) as cust_cnt from ads_cust_info_d a join dim_branch b on a.org_id=b.org_id where a.data_dt='20260531' group by b.up_org_name order by cust_cnt desc")
add("中等", "各城市客户数量前10名",
    "select city_name, count(*) as cust_cnt from ads_cust_info_d where data_dt='20260531' group by city_name order by cust_cnt desc limit 10")
add("中等", "2026年3月31日按省份统计客户总资产合计，降序",
    "select a.prov_name, sum(coalesce(b.nm_tot_aset,0)+coalesce(b.fc_pur_aset,0)) as tot_aset from ads_cust_info_d a left join dws_cust_aset_d b on a.pty_id=b.pty_id and b.data_dt='20260331' where a.data_dt='20260531' group by a.prov_name order by tot_aset desc")
add("中等", "按城市统计客户平均年龄，从高到低排序",
    "select city_name, round(avg(cust_age),2) as avg_age from ads_cust_info_d where data_dt='20260531' group by city_name order by avg_age desc")
add("中等", "2026年Q1各营业部客户总买入金额排名",
    "select c.up_org_name, c.org_name, sum(coalesce(b.buy_amt,0)) as buy_tot from ads_cust_info_d a join dwd_cust_tran_d b on a.pty_id=b.pty_id and b.data_dt between '20260101' and '20260331' join dim_branch c on a.org_id=c.org_id where a.data_dt='20260531' group by c.up_org_name, c.org_name order by buy_tot desc")
add("中等", "2026年Q1各产品二级分类的交易金额排名",
    "select p.prdt_type_name, sum(coalesce(t.buy_amt,0)+coalesce(t.sell_amt,0)) as tran_amt from dwd_cust_tran_d t join dim_product p on t.prdt_id=p.prdt_id where t.data_dt between '20260101' and '20260331' group by p.prdt_type_name order by tran_amt desc")
add("中等", "2026年3月31日持仓市值大于10万元的客户数量",
    "select count(*) as cust_cnt from (select pty_id from dwd_cust_hold_d where data_dt='20260331' group by pty_id having sum(coalesce(mkt_val,0))>100000) t")
add("中等", "2026年Q1交易金额大于50万元的客户数量",
    "select count(*) as cust_cnt from (select pty_id from dwd_cust_tran_d where data_dt between '20260101' and '20260331' group by pty_id having sum(coalesce(buy_amt,0)+coalesce(sell_amt,0))>500000) t")
add("中等", "统计各分公司女性客户数量",
    "select b.up_org_name, count(*) as cust_cnt from ads_cust_info_d a join dim_branch b on a.org_id=b.org_id where a.data_dt='20260531' and a.gender_cd='5000003' group by b.up_org_name order by cust_cnt desc")
add("中等", "统计各分公司钻石卡客户数量",
    "select b.up_org_name, count(*) as cust_cnt from ads_cust_info_d a join dim_branch b on a.org_id=b.org_id where a.data_dt='20260531' and a.cust_lvl_cd='1000001' group by b.up_org_name order by cust_cnt desc")
add("中等", "2026年3月31日按产品一级分类统计持仓客户数",
    "select p.up_prdt_type_name, count(distinct h.pty_id) as cust_cnt from dwd_cust_hold_d h join dim_product p on h.prdt_id=p.prdt_id where h.data_dt='20260331' group by p.up_prdt_type_name order by cust_cnt desc")
add("中等", "2026年3月31日持有债券产品的客户数量",
    "select count(distinct a.pty_id) as cust_cnt from dwd_cust_hold_d a join dim_product b on a.prdt_id=b.prdt_id where a.data_dt='20260331' and b.up_prdt_type_name='债券'")
add("中等", "2026年3月31日持有ETF产品的客户数量",
    "select count(distinct a.pty_id) as cust_cnt from dwd_cust_hold_d a join dim_product b on a.prdt_id=b.prdt_id where a.data_dt='20260331' and b.prdt_type_name='ETF'")
add("中等", "2026年3月31日持有科创板产品的客户数量",
    "select count(distinct a.pty_id) as cust_cnt from dwd_cust_hold_d a join dim_product b on a.prdt_id=b.prdt_id where a.data_dt='20260331' and b.prdt_type_name='科创板'")
add("中等", "各分公司客户平均年龄",
    "select b.up_org_name, round(avg(a.cust_age),2) as avg_age from ads_cust_info_d a join dim_branch b on a.org_id=b.org_id where a.data_dt='20260531' group by b.up_org_name order by avg_age desc")
add("中等", "2026年Q1买入金额排名前10的客户",
    "select pty_id, sum(coalesce(buy_amt,0)) as buy_tot from dwd_cust_tran_d where data_dt between '20260101' and '20260331' group by pty_id order by buy_tot desc limit 10")
add("中等", "2026年3月31日普通账户现金资产排名前10的客户",
    "select pty_id, coalesce(nm_bal,0) as bal from dws_cust_aset_d where data_dt='20260331' order by coalesce(nm_bal,0) desc limit 10")
add("中等", "2026年3月31日总资产排名前20的客户号和金额",
    "select pty_id, coalesce(nm_tot_aset,0)+coalesce(fc_pur_aset,0) as tot_aset from dws_cust_aset_d where data_dt='20260331' order by tot_aset desc limit 20")
add("中等", "统计各学历层级的男性客户数量",
    "select b.describe as edu_name, count(*) as cust_cnt from ads_cust_info_d a left join dim_public b on a.edu_cd=b.code and b.code_type_id='600' where a.data_dt='20260531' and a.gender_cd='5000002' group by b.describe order by cust_cnt desc")
add("中等", "统计各职业类型的客户平均年龄",
    "select b.describe as prof_name, round(avg(a.cust_age),2) as avg_age from ads_cust_info_d a left join dim_public b on a.prof_cd=b.code and b.code_type_id='700' where a.data_dt='20260531' group by b.describe order by avg_age desc")
add("中等", "2026年Q1各营业部客户总卖出金额排名",
    "select c.up_org_name, c.org_name, sum(coalesce(b.sell_amt,0)) as sell_tot from ads_cust_info_d a join dwd_cust_tran_d b on a.pty_id=b.pty_id and b.data_dt between '20260101' and '20260331' join dim_branch c on a.org_id=c.org_id where a.data_dt='20260531' group by c.up_org_name, c.org_name order by sell_tot desc")
add("中等", "2026年3月31日按产品二级分类统计持仓客户数",
    "select p.prdt_type_name, count(distinct h.pty_id) as cust_cnt from dwd_cust_hold_d h join dim_product p on h.prdt_id=p.prdt_id where h.data_dt='20260331' group by p.prdt_type_name order by cust_cnt desc")
add("中等", "统计各客户等级的男性客户数量",
    "select b.describe as cust_lvl_name, count(*) as cust_cnt from ads_cust_info_d a left join dim_public b on a.cust_lvl_cd=b.code and b.code_type_id='100' where a.data_dt='20260531' and a.gender_cd='5000002' group by b.describe order by cust_cnt desc")
add("中等", "2026年Q1各营业部客户总交易金额排名",
    "select c.up_org_name, c.org_name, sum(coalesce(b.buy_amt,0)+coalesce(b.sell_amt,0)) as tran_tot from ads_cust_info_d a join dwd_cust_tran_d b on a.pty_id=b.pty_id and b.data_dt between '20260101' and '20260331' join dim_branch c on a.org_id=c.org_id where a.data_dt='20260531' group by c.up_org_name, c.org_name order by tran_tot desc")


# ============================================================
# 较难（50 题）：官方4 + 旧题20 + 新题26
# ============================================================

# ---- 官方原题 4 道 ----
add("较难", "钻石卡男性客户，年龄大于40岁，持有比亚迪市值超过1000元，他在26年Q1的盈亏情况",
    """with custinfo as
(select pty_id
from ads_cust_info_d a
left join dim_public b on a.cust_lvl_cd=b.code and b.code_type_id='100'
left join dim_public c on a.gender_cd=c.code and c.code_type_id='500'
where b.describe='紫金理财钻石卡客户' and c.describe in ('男')
and a.cust_age>40
),
prdtinfo as
(select a.pty_id,sum(a.mkt_val) as mkt_val
from dwd_cust_hold_d a
inner join dim_product b on a.prdt_id=b.prdt_id
where b.prdt_name='比亚迪' and a.data_dt='20260331'
and exists(select 1 from custinfo z where a.pty_id=z.pty_id)
group by a.pty_id
having sum(a.mkt_val)>1000
)
select a.pty_id
     ,coalesce(c.nm_tot_aset,0)+coalesce(c.fc_pur_aset,0) as bgn_aset
     ,coalesce(b.nm_tot_aset,0)+coalesce(b.fc_pur_aset,0) as end_aset
     ,coalesce(d.aset_in,0) as aset_in
     ,coalesce(d.aset_out,0) as aset_out
     ,coalesce(b.nm_tot_aset,0)+coalesce(b.fc_pur_aset,0)-coalesce(c.nm_tot_aset,0)+coalesce(c.fc_pur_aset,0)+coalesce(d.aset_out,0)-coalesce(d.aset_in,0) as aset_pft
from prdtinfo a
left join dws_cust_aset_d b on a.pty_id=b.pty_id and b.data_dt='20260331'
left join dws_cust_aset_d c on a.pty_id=c.pty_id and c.data_dt='20260101'
left join
(
select pty_id
      ,sum(cash_in)+sum(tran_in)+sum(assign_in) as aset_in
      ,sum(cash_out)+sum(tran_out)+sum(assign_out) as aset_out
from dws_cust_fin_d
where data_dt between '20260101' and '20260331'
group by pty_id
) d on a.pty_id=d.pty_id""", source='official',
    reviewed_standard_sql="""with custinfo as
(select pty_id
from ads_cust_info_d a
left join dim_public b on a.cust_lvl_cd=b.code and b.code_type_id='100'
left join dim_public c on a.gender_cd=c.code and c.code_type_id='500'
where a.data_dt='20260531' and b.describe='紫金理财钻石卡客户' and c.describe='男'
and a.cust_age>40
), prdtinfo as
(select a.pty_id,sum(a.mkt_val) as mkt_val
from dwd_cust_hold_d a
inner join dim_product b on a.prdt_id=b.prdt_id
where b.prdt_name='比亚迪' and a.data_dt='20260331'
and exists(select 1 from custinfo z where a.pty_id=z.pty_id)
group by a.pty_id
having sum(a.mkt_val)>1000
)
select a.pty_id
     ,coalesce(c.nm_tot_aset,0)+coalesce(c.fc_pur_aset,0) as bgn_aset
     ,coalesce(b.nm_tot_aset,0)+coalesce(b.fc_pur_aset,0) as end_aset
     ,coalesce(d.aset_in,0) as aset_in
     ,coalesce(d.aset_out,0) as aset_out
     ,coalesce(b.nm_tot_aset,0)+coalesce(b.fc_pur_aset,0)-coalesce(c.nm_tot_aset,0)-coalesce(c.fc_pur_aset,0)+coalesce(d.aset_out,0)-coalesce(d.aset_in,0) as aset_pft
from prdtinfo a
left join dws_cust_aset_d b on a.pty_id=b.pty_id and b.data_dt='20260331'
left join dws_cust_aset_d c on a.pty_id=c.pty_id and c.data_dt='20260101'
left join
(
select pty_id
      ,sum(cash_in)+sum(tran_in)+sum(assign_in) as aset_in
      ,sum(cash_out)+sum(tran_out)+sum(assign_out) as aset_out
from dws_cust_fin_d
where data_dt between '20260101' and '20260331'
group by pty_id
) d on a.pty_id=d.pty_id""",
    review_status='approved',
    review_note='审核 SQL 已修正客户快照日期和盈亏公式，并已通过数据库执行验证。')

add("较难", "26年Q1交易过招商银行，且26年Q1末普通账户持有中国平安的客户",
    """with cust_tran as
(
select pty_id,prdt_id,sum(buy_amt) as buy_tot,sum(sell_amt) as sell_tot
from dwd_cust_tran_d
where data_dt between '20260101' and '20260331'
and prdt_id in (
select prdt_id from dim_product
where prdt_name='招商银行' and prdt_type_name='A股'
)
group by pty_id,prdt_id
)
select a.pty_id
from cust_tran a
inner join
(
select a.*
from dwd_cust_hold_d a
where prdt_id in (select prdt_id from dim_product where prdt_name='中国平安' and prdt_type_name='A股')
and a.data_dt='20260331' and a.sys_source='nm'
) b on a.pty_id=b.pty_id""", source='official')

add("较难", "26年Q1日均资产大于30万的客户，股票交易量大于10万的，其持有的产品属于哪些产品大类",
    """with cust_avg_30 as
(
select pty_id,round(sum(coalesce(nm_tot_aset,0)+coalesce(fc_pur_aset,0))/((to_date('20260331','yyyymmdd')-to_date('20260101','yyyymmdd'))::integer+1),2) as avg_aset
from dws_cust_aset_d
group by pty_id
having sum(coalesce(nm_tot_aset,0)+coalesce(fc_pur_aset,0))/((to_date('20260331','yyyymmdd')-to_date('20260101','yyyymmdd'))::integer+1)>300000
), cust_tran as
(
select a.pty_id,sum(b.buy_amt)+sum(b.sell_amt) as tran_amt
from dws_cust_aset_d a
left join dwd_cust_tran_d b on a.pty_id=b.pty_id and b.data_dt between '20260101' and '20260331'
inner join dim_product c on b.prdt_id=c.prdt_id and c.up_prdt_type_id='PT040000'
group by a.pty_id
having sum(b.buy_amt)+sum(b.sell_amt)>100000
)
select c.up_prdt_type_name,c.prdt_type_name,sum(mkt_val) as mkt_val
from cust_tran a
inner join dwd_cust_hold_d b on a.pty_id=b.pty_id and b.data_dt='20260331'
inner join dim_product c on b.prdt_id=c.prdt_id
group by c.prdt_type_name,c.up_prdt_type_name""", source='official',
    reviewed_standard_sql="""with cust_avg_30 as
(
select pty_id
from dws_cust_aset_d
where data_dt between '20260101' and '20260331'
group by pty_id
having sum(coalesce(nm_tot_aset,0)+coalesce(fc_pur_aset,0))/90>300000
), cust_tran as
(
select t.pty_id
from dwd_cust_tran_d t
inner join dim_product p on t.prdt_id=p.prdt_id
where t.data_dt between '20260101' and '20260331'
and p.up_prdt_type_name='股票'
group by t.pty_id
having sum(coalesce(t.buy_amt,0)+coalesce(t.sell_amt,0))>100000
)
select p.up_prdt_type_name,p.prdt_type_name,sum(coalesce(h.mkt_val,0)) as mkt_val
from cust_avg_30 a
inner join cust_tran t on a.pty_id=t.pty_id
inner join dwd_cust_hold_d h on a.pty_id=h.pty_id and h.data_dt='20260331'
inner join dim_product p on h.prdt_id=p.prdt_id
group by p.up_prdt_type_name,p.prdt_type_name""",
    review_status='approved',
    review_note='审核 SQL 已修正 Q1 日均资产、客户交集和交易额重复放大问题，并已通过数据库执行验证。')

add("较难", "查询26年1月10日到26年2月15日期间，科创板交易量大于25万的客户营业部分布情况",
    """select c.up_org_name,c.org_name,sum(b.tran_amt) as tran_amt
from ads_cust_info_d a
inner join
(
select a.pty_id,sum(buy_amt)+sum(sell_amt) as tran_amt
from dwd_cust_tran_d a
inner join dim_product b on a.prdt_id=b.prdt_id and b.prdt_type_name='科创板'
where a.data_dt between '20260110' and '20260215'
group by a.pty_id
having sum(buy_amt)+sum(sell_amt)>250000
) b on a.pty_id=b.pty_id
left join dim_branch c on a.org_id=c.org_id
group by c.up_org_name,c.org_name""", source='official')

# ---- 旧题保留 20 道 ----
add("较难", "总资产大于50万的男性客户，总持仓市值是多少",
    "with qualified_cust as (select a.pty_id from ads_cust_info_d a left join dim_public b on a.gender_cd = b.code and b.code_type_id='500' left join dws_cust_aset_d c on a.pty_id = c.pty_id and c.data_dt='20260331' where a.data_dt='20260531' and b.describe='男' and (coalesce(c.nm_tot_aset,0) + coalesce(c.fc_pur_aset,0)) > 500000) select coalesce(sum(a.mkt_val), 0) as tot_hold_val from dwd_cust_hold_d a inner join qualified_cust b on a.pty_id = b.pty_id where a.data_dt='20260331'")
add("较难", "2026年Q1交易金额前5的产品，对应交易金额和季末持仓市值",
    "with prdt_tran as (select b.prdt_name, sum(coalesce(a.buy_amt,0) + coalesce(a.sell_amt,0)) as tot_tran_amt from dwd_cust_tran_d a inner join dim_product b on a.prdt_id = b.prdt_id where a.data_dt between '20260101' and '20260331' group by b.prdt_name order by tot_tran_amt desc limit 5), prdt_hold as (select b.prdt_name, coalesce(sum(a.mkt_val), 0) as tot_hold_val from dwd_cust_hold_d a inner join dim_product b on a.prdt_id = b.prdt_id where a.data_dt='20260331' group by b.prdt_name) select a.prdt_name, a.tot_tran_amt, coalesce(b.tot_hold_val,0) as tot_hold_val from prdt_tran a left join prdt_hold b on a.prdt_name = b.prdt_name order by a.tot_tran_amt desc")
add("较难", "各分公司的客户总资产排名，从高到低",
    "select b.up_org_name, sum(coalesce(c.nm_tot_aset,0) + coalesce(c.fc_pur_aset,0)) as tot_aset from ads_cust_info_d a inner join dim_branch b on a.org_id = b.org_id left join dws_cust_aset_d c on a.pty_id = c.pty_id and c.data_dt='20260331' where a.data_dt='20260531' group by b.up_org_name order by tot_aset desc")
add("较难", "持有A股产品的客户中，本科及以上学历的客户占比",
    "with a_share_cust as (select distinct a.pty_id from dwd_cust_hold_d a inner join dim_product b on a.prdt_id = b.prdt_id where b.prdt_type_name='A股' and a.data_dt='20260331'), high_edu_cust as (select count(*) as cnt from a_share_cust a inner join ads_cust_info_d b on a.pty_id = b.pty_id left join dim_public c on b.edu_cd = c.code and c.code_type_id='600' where b.data_dt='20260531' and c.describe in ('学士','硕士','博士')) select (select cnt from high_edu_cust) * 1.0 / count(*) as high_edu_ratio from a_share_cust")
add("较难", "2026年3月各营业部客户总交易金额排名",
    "select c.up_org_name, c.org_name, sum(coalesce(b.buy_amt,0) + coalesce(b.sell_amt,0)) as tot_tran_amt from ads_cust_info_d a inner join dwd_cust_tran_d b on a.pty_id = b.pty_id and b.data_dt between '20260301' and '20260331' inner join dim_branch c on a.org_id = c.org_id where a.data_dt='20260531' group by c.up_org_name, c.org_name order by tot_tran_amt desc")
add("较难", "Q1有交易行为但季末无持仓的客户数量",
    "with tran_cust as (select distinct pty_id from dwd_cust_tran_d where data_dt between '20260101' and '20260331'), hold_cust as (select distinct pty_id from dwd_cust_hold_d where data_dt='20260331') select count(*) as cust_cnt from tran_cust a where not exists (select 1 from hold_cust b where a.pty_id = b.pty_id)")
add("较难", "钻石卡客户与普通客户的平均总资产差值",
    "with lvl_avg_aset as (select c.describe as cust_lvl, avg(coalesce(b.nm_tot_aset,0) + coalesce(b.fc_pur_aset,0)) as avg_aset from ads_cust_info_d a left join dws_cust_aset_d b on a.pty_id = b.pty_id and b.data_dt='20260331' left join dim_public c on a.cust_lvl_cd = c.code and c.code_type_id='100' where a.data_dt='20260531' group by c.describe) select (select avg_aset from lvl_avg_aset where cust_lvl='紫金理财钻石卡客户') - (select avg_aset from lvl_avg_aset where cust_lvl='紫金理财卡客户') as aset_diff")
add("较难", "按年龄段统计客户的平均持仓市值",
    "with cust_age_tag as (select pty_id, case when cust_age < 30 then '<30' when cust_age >= 30 and cust_age < 50 then '[30,50)' when cust_age >= 50 and cust_age < 60 then '[50,60)' when cust_age >= 60 then '[60,)' end as age_type from ads_cust_info_d where data_dt = '20260531'), cust_hold_total as (select pty_id, sum(coalesce(mkt_val, 0)) as total_mkt_val from dwd_cust_hold_d where data_dt = '20260331' group by pty_id) select a.age_type, round(avg(coalesce(b.total_mkt_val, 0)), 2) as avg_cust_hold_val from cust_age_tag a left join cust_hold_total b on a.pty_id = b.pty_id group by a.age_type order by a.age_type")
add("较难", "持仓产品数量大于5只的客户，平均总资产是多少",
    "with multi_prdt_cust as (select pty_id from dwd_cust_hold_d where data_dt='20260331' group by pty_id having count(distinct prdt_id) > 5) select avg(coalesce(b.nm_tot_aset,0) + coalesce(b.fc_pur_aset,0)) as avg_tot_aset from multi_prdt_cust a left join dws_cust_aset_d b on a.pty_id = b.pty_id and b.data_dt='20260331'")
add("较难", "各省份客户的整体交易佣金率",
    "select a.prov_name, sum(coalesce(b.buy_rake,0)+coalesce(b.sell_rake,0)) / nullif(sum(coalesce(b.buy_amt,0)+coalesce(b.sell_amt,0)),0) as avg_rake_rate from ads_cust_info_d a inner join dwd_cust_tran_d b on a.pty_id = b.pty_id and b.data_dt between '20260101' and '20260331' where a.data_dt='20260531' group by a.prov_name order by avg_rake_rate desc")
add("较难", "持有ETF产品的客户中，钻石卡客户占比",
    "with etf_cust as (select distinct a.pty_id from dwd_cust_hold_d a inner join dim_product b on a.prdt_id = b.prdt_id where a.data_dt='20260331' and b.prdt_type_name='ETF') select count(distinct case when c.cust_lvl_cd='1000001' then e.pty_id end) * 1.0 / count(distinct e.pty_id) as diamond_ratio from etf_cust e left join ads_cust_info_d c on e.pty_id = c.pty_id and c.data_dt='20260531'")
add("较难", "2026年Q1有资金转入但季末没有正资产的客户数量",
    "with fin_cust as (select distinct pty_id from dws_cust_fin_d where data_dt between '20260101' and '20260331' and (cash_in > 0 or tran_in > 0 or assign_in > 0)) select count(*) as cust_cnt from fin_cust f where not exists (select 1 from dws_cust_aset_d a where a.pty_id = f.pty_id and a.data_dt='20260331' and (coalesce(a.nm_tot_aset,0)+coalesce(a.fc_pur_aset,0)) > 0)")
add("较难", "各分公司客户的整体交易佣金率排名",
    "select d.up_org_name, sum(coalesce(b.buy_rake,0)+coalesce(b.sell_rake,0)) / nullif(sum(coalesce(b.buy_amt,0)+coalesce(b.sell_amt,0)),0) as avg_rake_rate from ads_cust_info_d a inner join dwd_cust_tran_d b on a.pty_id = b.pty_id and b.data_dt between '20260101' and '20260331' inner join dim_branch d on a.org_id = d.org_id where a.data_dt='20260531' group by d.up_org_name order by avg_rake_rate desc")
add("较难", "年龄大于60岁的女性客户，平均持仓市值是多少",
    "select avg(coalesce(h.total_mkt_val,0)) as avg_hold_mkt_val from ads_cust_info_d c left join (select pty_id, sum(mkt_val) as total_mkt_val from dwd_cust_hold_d where data_dt='20260331' group by pty_id) h on c.pty_id = h.pty_id where c.data_dt='20260531' and c.gender_cd='5000003' and c.cust_age > 60")
add("较难", "2026年Q1交易金额前10的客户，对应的客户等级和省份",
    "with tran_cust as (select pty_id, sum(coalesce(buy_amt,0)+coalesce(sell_amt,0)) as tot_tran_amt from dwd_cust_tran_d where data_dt between '20260101' and '20260331' group by pty_id order by tot_tran_amt desc limit 10) select t.pty_id, t.tot_tran_amt, d.describe as cust_lvl_name, c.prov_name from tran_cust t left join ads_cust_info_d c on t.pty_id = c.pty_id and c.data_dt='20260531' left join dim_public d on c.cust_lvl_cd = d.code and d.code_type_id='100' order by t.tot_tran_amt desc")
add("较难", "持有科创板产品的客户中，本科及以上学历的客户数量",
    "select count(distinct c.pty_id) as cust_cnt from dwd_cust_hold_d h inner join dim_product p on h.prdt_id = p.prdt_id inner join ads_cust_info_d c on h.pty_id = c.pty_id and c.data_dt='20260531' where h.data_dt='20260331' and p.prdt_type_name='科创板' and c.edu_cd in ('6000002','6000003','6000004')")
add("较难", "各营业部客户的平均总资产，前10名",
    "select b.up_org_name, b.org_name, avg(coalesce(a.nm_tot_aset,0)+coalesce(a.fc_pur_aset,0)) as avg_tot_aset from ads_cust_info_d c left join dws_cust_aset_d a on c.pty_id = a.pty_id and a.data_dt='20260331' inner join dim_branch b on c.org_id = b.org_id where c.data_dt='20260531' group by b.up_org_name, b.org_name order by avg_tot_aset desc limit 10")
add("较难", "2026年Q1买入金额大于卖出金额的客户数量",
    "select count(*) as cust_cnt from (select pty_id, sum(coalesce(buy_amt,0)) as total_buy, sum(coalesce(sell_amt,0)) as total_sell from dwd_cust_tran_d where data_dt between '20260101' and '20260331' group by pty_id having sum(coalesce(buy_amt,0)) > sum(coalesce(sell_amt,0))) t")
add("较难", "白金卡客户与金卡客户的平均持仓市值差值",
    "with lvl_hold as (select d.describe as cust_lvl, avg(coalesce(h.total_mkt_val,0)) as avg_hold_val from ads_cust_info_d a left join (select pty_id, sum(mkt_val) as total_mkt_val from dwd_cust_hold_d where data_dt='20260331' group by pty_id) h on a.pty_id = h.pty_id left join dim_public d on a.cust_lvl_cd = d.code and d.code_type_id='100' where a.data_dt='20260531' group by d.describe) select (select avg_hold_val from lvl_hold where cust_lvl='紫金理财白金卡客户') - (select avg_hold_val from lvl_hold where cust_lvl='紫金理财金卡客户') as hold_diff")
add("较难", "同时持有A股和债券产品的客户数量",
    "with a_share_cust as (select distinct pty_id from dwd_cust_hold_d a inner join dim_product b on a.prdt_id = b.prdt_id where a.data_dt='20260331' and b.prdt_type_name='A股'), bond_cust as (select distinct pty_id from dwd_cust_hold_d a inner join dim_product b on a.prdt_id = b.prdt_id where a.data_dt='20260331' and b.up_prdt_type_name='债券') select count(*) as cust_cnt from a_share_cust a where exists (select 1 from bond_cust b where a.pty_id = b.pty_id)")

# ---- 新题 26 道 ----
add("较难", "持有招商银行A股的客户数量",
    "select count(distinct a.pty_id) as cust_cnt from dwd_cust_hold_d a join dim_product b on a.prdt_id=b.prdt_id where a.data_dt='20260331' and b.prdt_name='招商银行' and b.prdt_type_name='A股'")
add("较难", "2026年Q1交易过中国平安A股的客户数量",
    "select count(distinct a.pty_id) as cust_cnt from dwd_cust_tran_d a join dim_product b on a.prdt_id=b.prdt_id where a.data_dt between '20260101' and '20260331' and b.prdt_name='中国平安' and b.prdt_type_name='A股'")
add("较难", "2026年Q1买入比亚迪金额大于5万元的客户数量",
    "select count(*) as cust_cnt from (select a.pty_id from dwd_cust_tran_d a join dim_product b on a.prdt_id=b.prdt_id where a.data_dt between '20260101' and '20260331' and b.prdt_name='比亚迪' group by a.pty_id having sum(coalesce(a.buy_amt,0))>50000) t")
add("较难", "同时持有招商银行和中国平安A股的客户数量",
    "select count(*) as cust_cnt from (select distinct a.pty_id from dwd_cust_hold_d a join dim_product b on a.prdt_id=b.prdt_id where a.data_dt='20260331' and b.prdt_name='招商银行' and b.prdt_type_name='A股') x where exists (select 1 from dwd_cust_hold_d c join dim_product d on c.prdt_id=d.prdt_id where c.data_dt='20260331' and c.pty_id=x.pty_id and d.prdt_name='中国平安' and d.prdt_type_name='A股')")
add("较难", "持有沪港通或深港通股票的客户数量",
    "select count(distinct a.pty_id) as cust_cnt from dwd_cust_hold_d a join dim_product b on a.prdt_id=b.prdt_id where a.data_dt='20260331' and b.prdt_type_name in ('沪港通','深港通')")
add("较难", "2026年Q1日均资产大于50万元的客户数量",
    "select count(*) as cust_cnt from (select pty_id from dws_cust_aset_d where data_dt between '20260101' and '20260331' group by pty_id having sum(coalesce(nm_tot_aset,0)+coalesce(fc_pur_aset,0))/90>500000) t")
add("较难", "2026年Q1日均资产排名前10的客户",
    "select pty_id, round(sum(coalesce(nm_tot_aset,0)+coalesce(fc_pur_aset,0))/90,2) as avg_aset from dws_cust_aset_d where data_dt between '20260101' and '20260331' group by pty_id order by avg_aset desc limit 10")
add("较难", "2026年Q1买入过贵州茅台A股的客户数量",
    "select count(distinct a.pty_id) as cust_cnt from dwd_cust_tran_d a join dim_product b on a.prdt_id=b.prdt_id where a.data_dt between '20260101' and '20260331' and b.prdt_name='贵州茅台' and b.prdt_type_name='A股'")
add("较难", "2026年Q1创业板交易量大于20万元的客户省份分布",
    "select c.prov_name, count(distinct t.pty_id) as cust_cnt from ads_cust_info_d c join (select a.pty_id from dwd_cust_tran_d a join dim_product b on a.prdt_id=b.prdt_id where a.data_dt between '20260101' and '20260331' and b.prdt_type_name='创业板' group by a.pty_id having sum(coalesce(a.buy_amt,0)+coalesce(a.sell_amt,0))>200000) t on c.pty_id=t.pty_id where c.data_dt='20260531' group by c.prov_name order by cust_cnt desc")
add("较难", "各分公司钻石卡客户占比",
    "select b.up_org_name, count(distinct case when a.cust_lvl_cd='1000001' then a.pty_id end)*1.0/count(distinct a.pty_id) as diamond_ratio from ads_cust_info_d a join dim_branch b on a.org_id=b.org_id where a.data_dt='20260531' group by b.up_org_name order by diamond_ratio desc")
add("较难", "2026年Q1有资金流出大于资金流入的客户数量",
    "select count(*) as cust_cnt from (select pty_id from dws_cust_fin_d where data_dt between '20260101' and '20260331' group by pty_id having sum(coalesce(cash_out,0)+coalesce(tran_out,0)+coalesce(assign_out,0)) > sum(coalesce(cash_in,0)+coalesce(tran_in,0)+coalesce(assign_in,0))) t")
add("较难", "2026年Q1净买入金额最大的前10位客户",
    "select pty_id, sum(coalesce(buy_amt,0))-sum(coalesce(sell_amt,0)) as net_buy from dwd_cust_tran_d where data_dt between '20260101' and '20260331' group by pty_id order by net_buy desc limit 10")
add("较难", "持有债券的客户中钻石卡客户占比",
    "select count(distinct case when c.cust_lvl_cd='1000001' then h.pty_id end)*1.0/count(distinct h.pty_id) as diamond_ratio from dwd_cust_hold_d h join dim_product p on h.prdt_id=p.prdt_id left join ads_cust_info_d c on h.pty_id=c.pty_id and c.data_dt='20260531' where h.data_dt='20260331' and p.up_prdt_type_name='债券'")
add("较难", "持有A股客户的男性占比",
    "select count(distinct case when c.gender_cd='5000002' then h.pty_id end)*1.0/count(distinct h.pty_id) as male_ratio from dwd_cust_hold_d h join dim_product p on h.prdt_id=p.prdt_id left join ads_cust_info_d c on h.pty_id=c.pty_id and c.data_dt='20260531' where h.data_dt='20260331' and p.prdt_type_name='A股'")
add("较难", "各年龄段客户的Q1总交易金额",
    "select case when c.cust_age<30 then '<30' when c.cust_age>=30 and c.cust_age<50 then '[30,50)' when c.cust_age>=50 and c.cust_age<60 then '[50,60)' else '[60,)' end as age_type, sum(coalesce(t.buy_amt,0)+coalesce(t.sell_amt,0)) as tran_amt from ads_cust_info_d c join dwd_cust_tran_d t on c.pty_id=t.pty_id and t.data_dt between '20260101' and '20260331' where c.data_dt='20260531' group by 1 order by 1")
add("较难", "2026年3月31日持仓市值大于总资产50%的客户数量",
    "select count(*) as cust_cnt from (select h.pty_id, sum(h.mkt_val) as hold_val from dwd_cust_hold_d h where h.data_dt='20260331' group by h.pty_id) x join dws_cust_aset_d a on x.pty_id=a.pty_id and a.data_dt='20260331' where x.hold_val > (coalesce(a.nm_tot_aset,0)+coalesce(a.fc_pur_aset,0))*0.5")
add("较难", "各分公司高净值客户（总资产大于100万）数量",
    "select b.up_org_name, count(distinct a.pty_id) as cust_cnt from dws_cust_aset_d a join ads_cust_info_d c on a.pty_id=c.pty_id and c.data_dt='20260531' join dim_branch b on c.org_id=b.org_id where a.data_dt='20260331' and (coalesce(a.nm_tot_aset,0)+coalesce(a.fc_pur_aset,0))>1000000 group by b.up_org_name order by cust_cnt desc")
add("较难", "持有科创板且总资产大于50万元的客户数量",
    "select count(distinct h.pty_id) as cust_cnt from dwd_cust_hold_d h join dim_product p on h.prdt_id=p.prdt_id join dws_cust_aset_d a on h.pty_id=a.pty_id and a.data_dt='20260331' where h.data_dt='20260331' and p.prdt_type_name='科创板' and (coalesce(a.nm_tot_aset,0)+coalesce(a.fc_pur_aset,0))>500000")
add("较难", "各产品一级分类的客户渗透率",
    "select p.up_prdt_type_name, count(distinct h.pty_id)*1.0/(select count(*) from ads_cust_info_d where data_dt='20260531') as penetration from dwd_cust_hold_d h join dim_product p on h.prdt_id=p.prdt_id where h.data_dt='20260331' group by p.up_prdt_type_name order by penetration desc")
add("较难", "2026年Q1按成交笔数排名前5的产品",
    "select p.prdt_name, sum(coalesce(t.buy_cnt,0)+coalesce(t.sell_cnt,0)) as trade_cnt from dwd_cust_tran_d t join dim_product p on t.prdt_id=p.prdt_id where t.data_dt between '20260101' and '20260331' group by p.prdt_name order by trade_cnt desc limit 5")
add("较难", "女性客户与男性客户的平均持仓市值差值",
    "with hold as (select pty_id, sum(mkt_val) as hv from dwd_cust_hold_d where data_dt='20260331' group by pty_id) select avg(case when c.gender_cd='5000003' then coalesce(h.hv,0) end) - avg(case when c.gender_cd='5000002' then coalesce(h.hv,0) end) as hold_diff from ads_cust_info_d c left join hold h on c.pty_id=h.pty_id where c.data_dt='20260531'")
add("较难", "各职业类型的高净值客户（总资产大于100万元）数量",
    "select b.describe as prof_name, count(distinct a.pty_id) as cust_cnt from dws_cust_aset_d a join ads_cust_info_d c on a.pty_id=c.pty_id and c.data_dt='20260531' left join dim_public b on c.prof_cd=b.code and b.code_type_id='700' where a.data_dt='20260331' and (coalesce(a.nm_tot_aset,0)+coalesce(a.fc_pur_aset,0))>1000000 group by b.describe order by cust_cnt desc")
add("较难", "上海分公司客户的2026年Q1总交易金额",
    "select sum(coalesce(t.buy_amt,0)+coalesce(t.sell_amt,0)) as tot_tran_amt from dwd_cust_tran_d t join ads_cust_info_d c on t.pty_id=c.pty_id and c.data_dt='20260531' join dim_branch b on c.org_id=b.org_id where b.up_org_name='上海分公司' and t.data_dt between '20260101' and '20260331'")
add("较难", "南京分公司客户的平均总资产",
    "select avg(coalesce(a.nm_tot_aset,0)+coalesce(a.fc_pur_aset,0)) as avg_aset from dws_cust_aset_d a join ads_cust_info_d c on a.pty_id=c.pty_id and c.data_dt='20260531' join dim_branch b on c.org_id=b.org_id where b.up_org_name='南京分公司' and a.data_dt='20260331'")
add("较难", "2026年Q1买入次数大于5次的客户数量",
    "select count(*) as cust_cnt from (select pty_id from dwd_cust_tran_d where data_dt between '20260101' and '20260331' group by pty_id having sum(coalesce(buy_cnt,0))>5) t")
add("较难", "持有ETF且2026年Q1有交易的客户数量",
    "select count(distinct h.pty_id) as cust_cnt from dwd_cust_hold_d h join dim_product p on h.prdt_id=p.prdt_id where h.data_dt='20260331' and p.prdt_type_name='ETF' and exists (select 1 from dwd_cust_tran_d t where t.pty_id=h.pty_id and t.data_dt between '20260101' and '20260331')")


# ============================================================
# 输出
# ============================================================
def main():
    # 校验数量
    from collections import Counter
    c = Counter(q['difficulty'] for q in Q)
    print("题目分布:", dict(c), "总:", len(Q))
    assert c['简单'] == 50 and c['中等'] == 50 and c['较难'] == 50, "数量不对"

    out = []
    for i, q in enumerate(Q, 1):
        out.append({"id": i, **q})

    path = os.path.join(os.path.dirname(__file__), 'test_questions.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("已写入:", path, "共", len(out), "题")


if __name__ == '__main__':
    main()
