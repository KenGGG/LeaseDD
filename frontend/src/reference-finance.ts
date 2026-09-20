// Observed reference row order. Values always come from local report evidence.
export type ReferenceRow={key:string;label:string;section:string;match?:string};
const row=(key:string,label:string,section:string,match?:string):ReferenceRow=>({key,label,section,match});
export const mainRows:ReferenceRow[]=[
 row('total_revenue','营业总收入','利润表','营业总收入'),row('total_revenue_growth','同比(%)','利润表','营业总收入同比'),
 row('revenue','营业收入','利润表'),row('revenue_growth','同比(%)','利润表'),row('total_profit','利润总额','利润表'),row('net_profit','净利润','利润表'),row('net_profit_growth','同比(%)','利润表'),row('net_profit_attributable_to_parent','归母净利润','利润表'),row('net_profit_attributable_to_parent_growth','同比(%)','利润表'),row('net_profit_excluding_nonrecurring','扣非后归母净利润','利润表'),row('asset_impairment_loss','资产减值损失','利润表'),row('credit_impairment_loss','信用减值损失','利润表'),
 row('total_assets','总资产','资产负债表'),row('total_assets_growth','同比(%)','资产负债表'),row('total_assets_quarter_growth','环比(%)','资产负债表'),row('total_liabilities','总负债','资产负债表'),row('total_liabilities_growth','同比(%)','资产负债表'),row('total_liabilities_quarter_growth','环比(%)','资产负债表'),row('short_debt','短期债务','资产负债表'),row('long_debt','长期债务','资产负债表'),row('interest_debt','有息债务','资产负债表'),row('total_equity','净资产','资产负债表'),row('total_equity_growth','同比(%)','资产负债表'),row('total_equity_quarter_growth','环比(%)','资产负债表'),row('parent_equity','归母净资产','资产负债表','归属于母公司所有者权益合计'),row('parent_equity_growth','同比(%)','资产负债表','归母净资产同比'),row('parent_equity_quarter_growth','环比(%)','资产负债表','归母净资产环比'),
 row('net_operating_cash_flow','经营现金流量净额','现金流量表'),row('net_investing_cash_flow','投资现金流量净额','现金流量表'),row('net_financing_cash_flow','筹资现金流量净额','现金流量表'),row('net_increase_in_cash','现金及现金等价物净增加额','现金流量表'),
 row('ending_cash_balance','期末现金及现金等价物余额','每股指标'),row('basic_eps','基本每股收益(元)','每股指标','基本每股收益'),row('diluted_eps','摊薄每股收益(元)','每股指标'),row('net_assets_per_share','每股净资产(元)','每股指标'),row('cash_per_share','每股经营现金流(元)','每股指标'),
 row('roe','净资产收益率(ROE)(%)','盈利能力'),row('roa','总资产收益率(ROA)(%)','盈利能力'),row('gross_margin','销售毛利率(%)','盈利能力'),row('net_margin','净利率(%)','盈利能力'),row('operating_margin','营业利润率(%)','盈利能力'),
 row('debt_ratio','资产负债率(%)','偿债能力'),row('current_ratio','流动比率(%)','偿债能力'),row('quick_ratio','速动比率(%)','偿债能力'),row('ebit_cover','EBIT保障倍数(倍)','偿债能力'),row('ebitda_cover','EBITDA保障倍数(倍)','偿债能力'),row('debt_ebitda','有息债务/EBITDA(倍)','偿债能力'),row('ebitda','EBITDA','偿债能力'),
];
export const analysisCategories=['每股指标','盈利能力','偿债能力','营运能力','成长能力','现金流量','杜邦分析'];
export const noteCategories=['审计报告','主营构成','主要销售客户','主要供应商','应收账款','预付款项','其他应收款','应付账款','预收款项','其他应付款','货币资金','存货','投资性房地产','受限资产','财务费用','非经常性损益','长期应收款'];

export const noteGroups:Record<string,string[]>={
 '应收账款':['应收账款账龄分析','前五名应收账款','计提坏账的重大应收账款'],
 '预付款项':['预付款项账龄分析','账龄超过1年的重要预付款','前五名预付款'],
 '其他应收款':['其他应收款按款项性质分类','其他应收款账龄分析','前五名其他应收款'],
 '应付账款':['应付账款账龄分析','账龄超过1年的重要应付账款','前五名应付款'],
 '预收款项':['预收款项账龄分析','账龄超过1年的重要预收款','前五名预收款'],
 '其他应付款':['其他应付款按款项性质分类','其他应付款账龄分析','账龄超过1年的重要其他应付款','前五名其他应付款'],
 '投资性房地产':['按成本计量','按公允价值计量'],
};
export const noteParent=(category:string)=>Object.entries(noteGroups).find(([,children])=>children.includes(category))?.[0]||category;
export const noteLabel=(category:string)=>category.endsWith('按款项性质分类')?'按款项性质分类':category;
