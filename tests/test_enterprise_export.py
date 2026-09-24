from io import BytesIO
from types import SimpleNamespace

import openpyxl

from leasedd.enterprise_export import export_enterprise_workbook


def test_indicator_trend_export_keeps_disclosed_yoy_and_one_scope_without_calculation():
    module=SimpleNamespace(module_key='main_indicators',module_name='主要财务指标',category='indicators',request_params={},raw_payload={},parsed_payload={
        'periods':['2025年年报','2025年年报','2024年年报'],'rows':[
            {'key':'dataType','name':'报表类型','values':['合并期末','母公司期末','合并期末']},
            {'key':'220006','name':'营业总收入','unit':'万元','values':['871649.239191','10000',None]},
            {'key':'220006_2','name':'同比','unit':'%','values':['14.495727','2',None]},
            {'key':'other','name':'无关科目','unit':'万元','values':['1','2','3']}]})
    book,values=rows(export_enterprise_workbook(module,trend_key='220006',report='annual',scopes='合并期末',unit='亿元'))
    assert values[0]==('序号','报告期','营业总收入（亿元）','同比（%）')
    assert values[1]==('1','2025年年报',87.1649239191,14.495727)
    assert values[2]==('2','2024年年报',None,None)
    assert module.parsed_payload['rows'][1]['values'][2] is None
    book.close()


def test_indicator_trend_export_rejects_unknown_rows_and_ambiguous_scope():
    import pytest
    module=SimpleNamespace(module_key='main_indicators',module_name='主要财务指标',category='indicators',request_params={},raw_payload={},parsed_payload={
        'periods':['2025年年报'],'rows':[{'key':'220006','name':'营业总收入','values':['1']}]})
    for options in ({'trend_key':'unknown','scopes':'合并期末'}, {'trend_key':'220006','scopes':'all'}, {'trend_key':'220006','scopes':'合并期末','report':'all'}):
        with pytest.raises(ValueError,match='invalid_trend_options'):
            export_enterprise_workbook(module,**options)


def test_balance_trend_excel_uses_disclosed_ratio_columns_not_asset_amount():
    module=SimpleNamespace(module_key='balance_sheet',module_name='资产负债表',category='statements',request_params={},raw_payload={},parsed_payload={
        'periods':['2025年年报']*6,'rows':[
            {'key':'dataType','name':'报表类型','values':['合并期末','合并期末较年初比(%)','合并期末同比(%)','合并期末销售比(%)','合并期末资产比(%)','合并期末环比(%)']},
            {'key':'110050','name':'资产总计','unit':'万元','values':['1681573.338932','-5.576781','-5.576781','192.918580','100','-0.536379']}]})
    book,values=rows(export_enterprise_workbook(module,trend_key='110050',report='annual',scopes='合并期末'))
    assert values[0]==('序号','报告期','资产总计(%)','同比增长率(%)','销售百分比(%)','资产百分比(%)','环比增长率(%)')
    assert values[1]==('1','2025年年报',-5.576781,-5.576781,192.91858,100,-0.536379)
    book.close()


def test_income_trend_excel_keeps_amount_unit_and_source_ratios():
    module=SimpleNamespace(module_key='income_statement',module_name='利润表',category='statements',request_params={},raw_payload={},parsed_payload={
        'periods':['2025年年报']*3,'rows':[
            {'key':'dataType','name':'报表类型','values':['合并期末','合并期末同比(%)','合并期末销售比(%)']},
            {'key':'displayCurrency','name':'币种','values':['人民币']*3},
            {'key':'120050','name':'营业收入','unit':'万元','values':['871649.239191','14.495727',None]}]})
    book,values=rows(export_enterprise_workbook(module,trend_key='120050',report='annual',scopes='合并期末',unit='亿元'))
    assert values[0]==('序号','报告期','营业收入（亿元人民币）','同比增长率(%)','销售百分比(%)')
    assert values[1]==('1','2025年年报',87.1649239191,14.495727,None)
    book.close()


def test_statement_trend_export_rejects_ambiguous_accounting_key():
    import pytest
    module=SimpleNamespace(module_key='cash_flow_statement',module_name='现金流量表',category='statements',request_params={},raw_payload={},parsed_payload={
        'periods':['2025年年报'],'rows':[
            {'key':'dataType','values':['合并期末']},
            {'key':'130065','name':'主表项目','values':['1']},
            {'key':'130065','name':'补充披露','values':['2']}]})
    with pytest.raises(ValueError,match='invalid_trend_options'):
        export_enterprise_workbook(module,trend_key='130065',report='annual',scopes='合并期末')


def test_trend_export_currency_comes_from_selected_period_cells():
    module=SimpleNamespace(module_key='main_indicators',module_name='主要财务指标',category='indicators',request_params={},raw_payload={},parsed_payload={
        'periods':['2025年年报','2024年年报'],'rows':[
            {'key':'dataType','name':'报表类型','values':['合并期末','合并期末']},
            {'key':'displayCurrency','name':'显示币种','values':['美元','美元']},
            {'key':'220006','name':'营业总收入','unit':'万元','values':['10000','20000']},
            {'key':'220006_2','name':'同比','unit':'%','values':['3','4']}]})
    options={'trend_key':'220006','report':'annual','scopes':'合并期末','unit':'亿元'}
    book,values=rows(export_enterprise_workbook(module,**options))
    assert values[0]==('序号','报告期','营业总收入（亿元美元）','同比（%）')
    book.close()
    module.parsed_payload['rows'][1]['values']=['美元','人民币']
    book,values=rows(export_enterprise_workbook(module,**options))
    assert values[0]==('序号','报告期','营业总收入（亿元）','同比（%）','币种')
    assert values[1][-1]=='美元' and values[2][-1]=='人民币'
    assert values[1][2]==1 and values[2][2]==2
    book.close()


def test_currency_selection_uses_saved_variant_not_a_local_exchange_rate():
    from leasedd.enterprise_export import select_currency_variant
    module=SimpleNamespace(module_name='资产负债表',module_key='balance_sheet',category='statements',request_params={},response_sha256='a'*64,
        raw_payload={'responses':[{'payload':{'data':'source-usd'}}]},
        parsed_payload={'variants':[{'request_params':{'displayCurrency':'USD','rateType':'2'},'parsed':{'periods':['2025年年报'],'rows':[{'name':'资产','values':['14.25']}]}}]})
    selected=select_currency_variant(module,'USD','2')
    assert selected.parsed_payload['rows'][0]['values']==['14.25']
    assert selected.raw_payload=={'data':'source-usd'}
    assert selected.request_params['displayCurrency']=='USD'
    import pytest
    with pytest.raises(ValueError):select_currency_variant(module,'EUR','1')


def test_source_disabled_module_cannot_be_exported_as_an_empty_financial_report():
    import pytest
    module=SimpleNamespace(parsed_payload={'rows':[],'metadata':{'unavailable':True}})
    with pytest.raises(ValueError,match='source_module_unavailable'):
        export_enterprise_workbook(module)


def test_export_supports_source_toolbar_billion_yuan_unit():
    module=SimpleNamespace(module_name='资产负债表',category='statements',request_params={},raw_payload={},
        parsed_payload={'periods':['2025年年报'],'rows':[{'name':'资产','unit':'万元','values':['100000']}]})
    book,values=rows(export_enterprise_workbook(module,unit='十亿元'))
    assert values[2][2]==1
    book.close()


def test_excel_converts_provider_scientific_amount_without_changing_raw_value():
    module=SimpleNamespace(module_name='利润表',category='statements',request_params={},raw_payload={},
        parsed_payload={'periods':['2020年中报'],'rows':[{'name':'营业外收入','unit':'万元','values':['8.0E-6']}]})
    book,values=rows(export_enterprise_workbook(module,unit='元'))
    assert values[2][2]==0.08
    assert module.parsed_payload['rows'][0]['values'][0]=='8.0E-6'
    book.close()


def test_export_three_year_window_matches_source_quarter_cutoff_not_calendar_years():
    module=SimpleNamespace(module_name='资产负债表',category='statements',request_params={},raw_payload={},
        parsed_payload={'periods':['2026年中报','2023年三季报','2023年中报'],'rows':[{'name':'资产','unit':'万元','values':['1','2','3']}]})
    book,values=rows(export_enterprise_workbook(module,window_years=3))
    assert values[1][2:]==('2026年中报','2023年三季报')
    assert values[2][2:]==(1,2)
    book.close()


def rows(content):
    book = openpyxl.load_workbook(BytesIO(content), data_only=False)
    return book, list(book.active.values)


def test_business_export_filters_standalone_types_and_uses_request_unit_only_for_amounts():
    module=SimpleNamespace(module_key='main_business',module_name='主营构成',category='notes',request_params={'unitCode':'4'},raw_payload={},parsed_payload={
        'periods':['2025年年报']*3,'rows':[
            {'key':'dataType','name':'数据类型','values':['原始报表','同比','占收入比']},
            {'key':'120050','name':'营业收入','unit':'','values':['10000','12.5','100']},
            {'key':'900042','name':'毛利率(%)','unit':'','values':['20','2','3']},
            {'key':'conversionRate','name':'转换汇率','unit':'','values':['7','7','7']}]})
    book,values=rows(export_enterprise_workbook(module,unit='亿元'))
    assert values[1][:2]==('序号','项目名称')
    assert next(row[2:] for row in values if row[1]=='营业收入(亿元)')==(1,12.5,100)
    assert next(row[2:] for row in values if row[1]=='毛利率(%)')==(20,2,3)
    assert next(row[2:] for row in values if row[1]=='转换汇率')==(7,7,7)
    book.close()
    book,values=rows(export_enterprise_workbook(module,unit='亿元',data_kinds='同比'))
    assert next(row[2:] for row in values if row[1]=='营业收入(亿元)')==(12.5,)
    book.close()


def test_receivables_record_export_filters_periods_like_screen_without_changing_source_values():
    module=SimpleNamespace(module_key='receivables_top_five',module_name='前五名应收账款',category='notes',request_params={},raw_payload={},parsed_payload={
        'head':[['单位名称','第一名']]*4,
        'rows':[[['账面余额','6.81亿']],[['账面余额','5.92亿']],[['账面余额','4.00亿']],[['账面余额','3.00亿']]],
        'metadata':{'report':['20251231','20250630','20231231','20211231']}})
    original=str(module.parsed_payload)
    book,values=rows(export_enterprise_workbook(module,report='annual',window_years=3,descending=False))
    assert [row[0] for row in values if row[0] and '年' in str(row[0])]==['2023年年报','2025年年报']
    assert values[-1]==('第一名','6.81亿')
    assert str(module.parsed_payload)==original
    book.close()
    book,values=rows(export_enterprise_workbook(module,report='half',start='2025'))
    assert [row[0] for row in values if row[0] and '年' in str(row[0])]==['2025年中报']
    assert values[-1]==('第一名','5.92亿')
    book.close()


def test_precise_receivables_excel_uses_saved_full_value_and_declared_source_unit():
    module=SimpleNamespace(module_key='receivables_top_five',module_name='前五名应收账款',category='notes',
                           request_params={'unit':'万元'},raw_payload={},parsed_payload={
        'head':[['单位名称','第一名']],
        'rows':[[['期末余额','68137.782993'],['占总额比例(%)','28.14']]],
        'metadata':{'report':['2025年年报'],'precise_record':True}})
    book,values=rows(export_enterprise_workbook(module,unit='元',decimals=2))
    assert values[1]==('序号','单位名称','期末余额(元)','占总额比例(%)')
    assert values[3]==('2','第一名',681377829.93,28.14)
    assert book.active['C4'].number_format=='###,###,##0.00'
    assert module.parsed_payload['rows'][0][0][1]=='68137.782993'
    book.close()


def test_precise_receivables_source_export_omits_tags_outside_selected_years():
    module=SimpleNamespace(module_key='receivables_top_five',module_name='前五名应收账款',category='notes',
                           request_params={'unit':'万元'},
                           raw_payload={'data':{'head':['单位名称','2025年年报','第一名','2019年年报','旧客户']}},
                           parsed_payload={
        'head':[['单位名称','第一名'],['单位名称','旧客户']],
        'rows':[[['期末余额','68137.782993'],['占总额比例(%)','28.14111'],['年增长率(%)','-8.075923']],
                [['期末余额','100'],['占总额比例(%)','1'],['年增长率(%)','2']]],
        'metadata':{'report':['2025年年报','2019年年报'],'precise_record':True,
                    'companyTag':[[],[],[],[],['民企']]}})
    book,values=rows(export_enterprise_workbook(module,report='latest,annual',window_years=5))
    assert values==[
        ('数据来源：企业预警通',None,None,None,None),
        ('序号','单位名称','期末余额(万元)','占总额比例(%)','年增长率(%)'),
        ('1','2025年年报',None,None,None),
        ('2','第一名',68137.782993,28.14111,-8.075923)]
    assert book.active['A4'].data_type=='s'
    assert book.active['C4'].number_format=='###,###,##0.00'
    assert module.parsed_payload['metadata']['companyTag'][-1]==['民企']
    book.close()


def test_precise_other_receivables_source_export_aligns_selected_row_tags():
    module=SimpleNamespace(module_key='other_receivables_top_five',module_name='前五名其他应收款',category='notes',
                           request_params={'unit':'万元'},
                           raw_payload={'data':{'head':['单位名称','2025年年报','公司甲','公司乙']}},
                           parsed_payload={
        'head':[['单位名称','公司甲','公司乙']],
        'rows':[[['期末余额','906.826905','281.55986'],['占总额比例(%)','37.7','11.71'],
                 ['年增长率(%)',None,None]]],
        'metadata':{'report':['2025年年报'],'precise_record':True,
                    'companyTag':[[],[],[],['民企']]}})
    book,values=rows(export_enterprise_workbook(module,report='latest,annual',window_years=5))
    assert values==[
        ('数据来源：企业预警通',None,None,None,None,None),
        ('序号','单位名称','期末余额(万元)','占总额比例(%)','年增长率(%)','企业类型标签'),
        ('1','2025年年报',None,None,None,None),
        ('2','公司甲',906.826905,37.7,None,None),
        ('3','公司乙',281.55986,11.71,None,'民企')]
    assert book.active['F5'].data_type=='s'
    assert module.parsed_payload['metadata']['companyTag'][-1]==['民企']
    book.close()


def test_impairment_record_excel_keeps_source_serial_amounts_and_aligned_tags():
    module=SimpleNamespace(module_key='receivables_impairment',module_name='计提坏账的重大应收账款',category='notes',
                           request_params={},raw_payload={},parsed_payload={
        'head':[['单位名称','东莞市迈科新能源有限公司','合肥锂能科技有限公司']],
        'rows':[[['账面余额','433.97万','11.89万'],['坏账准备','433.97万','11.89万'],['账面价值','-','-']]],
        'metadata':{'report':['20240630'],
                    'companyTag':[['',['民企'],['民企']]],
                    'negativeTag':[['',['失信','终本案件'],['终本案件']]]}})
    book,values=rows(export_enterprise_workbook(module))
    assert values==[
        ('数据来源：企业预警通',None,None,None,None,None,None),
        ('序号','单位名称','账面余额','坏账准备','账面价值','企业类型标签','负面信息标签'),
        ('1','2024年中报',None,None,None,None,None),
        ('2','东莞市迈科新能源有限公司',433.97,433.97,None,'民企','失信 终本案件'),
        ('3','合肥锂能科技有限公司',11.89,11.89,None,'民企','终本案件')]
    assert book.active['C4'].number_format=='###,###,##0.00"万"'
    assert book.active['A4'].data_type=='s'
    assert module.parsed_payload['rows'][0][0][1]=='433.97万'
    book.close()


def test_other_impairment_excel_uses_only_source_company_tag_column():
    module=SimpleNamespace(module_key='other_receivables_impairment',module_name='计提坏账的重大其他应收款',category='notes',
                           request_params={},raw_payload={},parsed_payload={
        'head':[['单位名称','广东科萝机械设备有限公司','成都兆雄智能设备有限公司','合计']],
        'rows':[[['账面余额','2.30万','281.56万','283.86万'],
                 ['坏账准备','2.30万','281.56万','283.86万'],['账面价值','-','-','-']]],
        'metadata':{'report':['20260630'],'companyTag':[['',[],['民企'],[]]]}})
    book,values=rows(export_enterprise_workbook(module))
    assert values==[
        ('数据来源：企业预警通',None,None,None,None,None),
        ('序号','单位名称','账面余额','坏账准备','账面价值','企业类型标签'),
        ('1','2026年中报',None,None,None,None),
        ('2','广东科萝机械设备有限公司',2.3,2.3,None,None),
        ('3','成都兆雄智能设备有限公司',281.56,281.56,None,'民企'),
        ('4','合计',283.86,283.86,None,None)]
    assert book.active['C4'].number_format=='###,###,##0.00"万"'
    assert book.active['A4'].data_type=='s'
    book.close()


def test_source_record_excel_adds_provenance_and_text_serial_without_rewriting_values():
    cases=(
        ('major_customers','主要销售客户','客户名称','销售额','占销售总额比例','34.03亿','39.03%'),
        ('major_suppliers','主要供应商','客户名称','采购额','占采购总额比例','10.26亿','13.02%'),
        ('prepayments_top_five','前五名预付款','单位名称','账面余额','占总额比例','2,975.86万','37.36%'),
    )
    for key,name,label,amount_label,ratio_label,amount,ratio in cases:
        module=SimpleNamespace(module_key=key,module_name=name,category='notes',request_params={},raw_payload={},parsed_payload={
            'head':[[label,'第一名']],
            'rows':[[[amount_label,amount],[ratio_label,ratio]]],
            'metadata':{'report':['20251231']}})
        book,values=rows(export_enterprise_workbook(module))
        assert values==[
            ('数据来源：企业预警通',None,None,None),
            ('序号',label,amount_label,ratio_label),
            ('1','2025年年报',None,None),
            ('2','第一名',amount,ratio)]
        assert book.active['A4'].data_type=='s'
        assert book.active['C4'].data_type=='s'
        book.close()


def test_other_payables_over_one_year_excel_matches_observed_source_layout():
    module=SimpleNamespace(module_key='other_payables_over_one_year',module_name='账龄超过1年的重要其他应付款',
                           category='notes',request_params={},raw_payload={},parsed_payload={
        'head':[['项目名称','单位1','合计']],
        'rows':[[['账面余额','2.69万','2.69万'],['占总额比例','0.06%','0.06%']]],
        'metadata':{'report':['20200630']}})
    book,values=rows(export_enterprise_workbook(module,report='latest,annual'))
    assert values==[
        ('数据来源：企业预警通',None,None,None),
        ('序号','项目名称','账面余额','占总额比例'),
        ('1','2020年中报',None,None),
        ('2','单位1','2.69万','0.06%'),
        ('3','合计','2.69万','0.06%')]
    assert book.active['A4'].data_type=='s'
    assert module.parsed_payload['rows'][0][0][1]=='2.69万'
    book.close()


def test_receivables_aging_excel_preserves_source_row_numbers_and_numeric_units():
    module=SimpleNamespace(module_key='receivables_aging',module_name='应收账款账龄分析',category='notes',
                           request_params={},raw_payload={},parsed_payload={
        'head':['账龄','1年内','空行','合计'],
        'rows':[['20251231','22.99亿','- ','23.00亿'],
                ['20241231','16.77亿','', '16.77亿']],
        'metadata':{}})
    book,values=rows(export_enterprise_workbook(module,report='annual'))
    assert values==[
        ('数据来源：企业预警通',None,None,None),
        ('序号','账龄','2025年年报','2024年年报'),
        ('1','1年内',22.99,16.77),
        ('3','合计',23,16.77)]
    assert book.active['A4'].data_type=='s'
    assert book.active['C3'].number_format=='###,###,##0.00"亿"'
    assert module.parsed_payload['rows'][0][1]=='22.99亿'
    book.close()


def test_other_verified_flat_notes_keep_raw_units_even_if_source_excel_format_is_wrong():
    cases=(
        ('prepayments_aging','账龄','2.07亿','###,###,##0.00"亿"',2.07),
        ('other_receivables_aging','账龄','4,500.00元','###,###,##0.00"元"',4500),
        ('nonrecurring_gains_losses','项目名称','-1,919.27万','###,###,##0.00"万"',-1919.27),
    )
    for key,label,raw,number_format,amount in cases:
        module=SimpleNamespace(module_key=key,module_name=key,category='notes',request_params={},raw_payload={},parsed_payload={
            'head':[label,'第一项','空行'],
            'rows':[['20251231',raw,'- ']],
            'metadata':{}})
        book,values=rows(export_enterprise_workbook(module,report='latest,annual'))
        assert values==[
            ('数据来源：企业预警通',None,None),
            ('序号',label,'2025年年报'),
            ('1','第一项',amount)]
        assert book.active['A3'].data_type=='s'
        assert book.active['C3'].number_format==number_format
        assert module.parsed_payload['rows'][0][1]==raw
        book.close()


def test_payables_aging_exports_keep_source_periods_and_numeric_unit_cells():
    cases=(
        ('payables_aging',['20160630','20151231'],
         ['4,969.19万','2,167.40万'],['110.76万','123.14万'],
         ('序号','账龄','2016年中报','2015年年报'),('1','1年内',4969.19,2167.4)),
        ('other_payables_aging',['20151231','20141231'],
         ['1,792.14万','469.87万'],['3.08万','283.66万'],
         ('序号','账龄','2015年年报','2014年年报'),('1','1年内',1792.14,469.87)),
    )
    for key,periods,first,second,header,first_output in cases:
        module=SimpleNamespace(module_key=key,module_name=key,category='notes',
                               request_params={},raw_payload={},parsed_payload={
            'head':['账龄','1年内','1-2年'],
            'rows':[[periods[i],first[i],second[i]] for i in range(2)],
            'metadata':{}})
        book,values=rows(export_enterprise_workbook(module,report='latest,annual'))
        assert values==[
            ('数据来源：企业预警通',None,None,None),
            header,
            first_output,
            ('2','1-2年',110.76 if key=='payables_aging' else 3.08,
             123.14 if key=='payables_aging' else 283.66)]
        assert book.active['A3'].data_type=='s'
        assert book.active['C3'].number_format=='###,###,##0.00"万"'
        assert module.parsed_payload['rows'][0][1]==first[0]
        book.close()


def test_other_receivables_property_exports_keep_nonconsecutive_source_row_numbers():
    module=SimpleNamespace(module_key='other_receivables_property',module_name='按款项性质分类',
                           category='notes',request_params={},raw_payload={},parsed_payload={
        'head':['项目名称','备用金','往来款','保证金及押金','代付代垫款','借款',
                '退税','股权转让款','工程款','拆借款','坏账准备','土地款',
                '租金','关联方往来','其他','合计'],
        'rows':[['20220630','','','1,286.46万','','112.20万','','','','','','','','','97.51万','1,496.16万'],
                ['20211231','','','1,827.25万','','94.48万','','','','','','','','','101.53万','2,023.26万']],
        'metadata':{}})
    book,values=rows(export_enterprise_workbook(module,report='latest,annual'))
    assert values==[
        ('数据来源：企业预警通',None,None,None),
        ('序号','项目名称','2022年中报','2021年年报'),
        ('3','保证金及押金',1286.46,1827.25),
        ('5','借款',112.2,94.48),
        ('14','其他',97.51,101.53),
        ('15','合计',1496.16,2023.26)]
    assert book.active['A3'].data_type=='s'
    assert book.active['C3'].number_format=='###,###,##0.00"万"'
    assert module.parsed_payload['rows'][0][3]=='1,286.46万'
    book.close()


def test_restricted_assets_excel_numbers_only_visible_rows_like_source():
    module=SimpleNamespace(module_key='restricted_assets',module_name='受限资产',category='notes',request_params={},raw_payload={},parsed_payload={
        'periods':['2026年中报'],
        'rows':[
            {'key':'deadline','name':'截止日期','values':['2026-06-30']},
            {'key':'moneyFunds','name':'货币资金','values':['157841.954409']},
            {'key':'empty','name':'其他流动资产','values':[None]},
            {'key':'fixedAssets','name':'固定资产','values':['274736.654869']}],
        'metadata':{'headExport':['报告期','截止日期','货币资金（万元）','其他流动资产（万元）','固定资产（万元）']}})
    book,values=rows(export_enterprise_workbook(module,report='latest,annual'))
    assert values==[
        ('数据来源：企业预警通',None,None),
        ('序号','报告期','2026年中报'),
        ('1','截止日期','2026-06-30'),
        ('2','货币资金（万元）',157841.954409),
        ('3','固定资产（万元）',274736.654869)]
    assert book.active['A5'].data_type=='s'
    assert book.active['C4'].number_format=='###,###,##0.00'
    assert module.parsed_payload['rows'][1]['values'][0]=='157841.954409'
    book.close()


def test_important_payables_excel_keeps_source_row_numbers_and_text_values():
    module=SimpleNamespace(module_key='payables_over_one_year',module_name='账龄超过1年的重要应付账款',
                           category='notes',request_params={},raw_payload={},parsed_payload={
        'head':[['项目名称','供应商一','供应商二','合计']],
        'rows':[[['账面余额','7,995.97万','5,834.27万','1.38亿'],
                 ['占总额比例','2.33%','1.70%','4.02%']]],
        'metadata':{'report':['20260630']}})
    book,values=rows(export_enterprise_workbook(module))
    assert values==[
        ('数据来源：企业预警通',None,None,None),
        ('序号','项目名称','账面余额','占总额比例'),
        ('1','2026年中报',None,None),
        ('2','供应商一','7,995.97万','2.33%'),
        ('3','供应商二','5,834.27万','1.70%'),
        ('4','合计','1.38亿','4.02%')]
    assert book.active['A4'].data_type=='s'
    assert book.active['C4'].data_type=='s'
    assert module.parsed_payload['rows'][0][0][1]=='7,995.97万'
    book.close()


def test_main_business_excel_renumbers_selected_period_rows_but_counts_hidden_sibling():
    module=SimpleNamespace(module_key='main_business',module_name='主营构成',category='notes',
                           request_params={'unitCode':'4'},raw_payload={},parsed_payload={
        'periods':['2025年年报','2020年年报'],
        'rows':[
            {'key':'dataType','name':'数据类型','values':['原始报表','原始报表']},
            {'key':'deadline','name':'截止日期','values':['2025-12-31','2020-12-31']},
            {'key':'120050','name':'营业收入','level':1,'values':['100','50']},
            {'key':'incomePrefix_310000','name':'产品','level':2,'values':['100','50']},
            {'key':'incomePrefix_999','name':'历史产品','level':3,'values':[None,'50']},
            {'key':'incomePrefix_123','name':'细分产品','level':3,'values':['100',None]},
            {'key':'costPrefix_123','name':'细分产品','level':3,'values':[None,None]},
            {'key':'profitPrefix_123','name':'细分产品','level':3,'unit':'%','values':[None,None]},
            {'key':'conversionRate','name':'转换汇率','values':['1','1']}],
        'metadata':{'blankNum':[0,0,0,0,2,3,3,3,3,0]}})
    book,values=rows(export_enterprise_workbook(module,report='latest,annual',window_years=5,data_kinds='原始报表'))
    assert values==[
        ('数据来源：企业预警通',None,None),
        ('序号','项目名称','2025年年报'),
        ('1','数据类型','原始报表'),
        ('2','截止日期','2025-12-31'),
        ('3','营业收入(万元)',100),
        ('4','    产品(万元)',100),
        ('5','      细分产品(万元)',100),
        ('8','转换汇率',1)]
    assert book.active['A8'].data_type=='s'
    assert book.active['C8'].number_format=='General'
    assert module.parsed_payload['rows'][5]['values'][0]=='100'
    book.close()


def test_export_is_real_xlsx_and_uses_selected_periods_and_exact_display_units():
    module = SimpleNamespace(module_name='资产负债表', category='statements', request_params={}, raw_payload={},
        parsed_payload={'periods':['2026年中报','2025年年报','2024年年报'], 'rows':[
            {'key':'cash','name':'货币资金','unit':'元','values':['1039981.78','0',None]},
            {'key':'unsafe','name':'=HYPERLINK("bad")','unit':'','values':[None,None,None]},
        ], 'metadata':{'headExport':['指标名称','货币资金（万元）','其他']}})
    original = str(module.parsed_payload)
    content = export_enterprise_workbook(module, report='annual', start='2025', unit='亿元', decimals=2)
    assert content.startswith(b'PK')
    book, values = rows(content)
    assert values == [('数据来源：企业预警通',None,None),('序号','指标名称','2025年年报'),(1,'货币资金（亿元）',0)]
    assert book.active.freeze_panes == 'C3'
    assert book.active['C3'].number_format == '#,##0.00'
    assert str(module.parsed_payload) == original
    book.close()


def test_mixed_percentage_columns_are_not_scaled_by_amount_unit():
    module=SimpleNamespace(module_name='资产负债表',category='statements',request_params={},raw_payload={},parsed_payload={
        'periods':['2025年年报','2025年年报'],'rows':[
            {'name':'报表类型','key':'dataType','values':['合并期末','合并期末同比(%)']},
            {'name':'资产总计','key':'assets','unit':'万元','values':['10000','12.5']}]})
    book,values=rows(export_enterprise_workbook(module,unit='亿元'))
    assert values[-1][2:]==(1,12.5)
    book.close()
    book,values=rows(export_enterprise_workbook(module,unit='亿元',scopes='合并期末',data_kinds='同比增长率'))
    assert values[-1][2:]==(12.5,)
    book.close()


def test_analysis_export_filters_report_range_metadata():
    module=SimpleNamespace(module_name='盈利能力',category='analysis',request_params={},raw_payload={},parsed_payload={
        'periods':['2025年年报','2025年年报'],'rows':[
            {'name':'报表类型','key':'reportRange','values':['合并期末','母公司期末']},
            {'name':'净利率','key':'ratio','unit':'%','values':['10','8']}]})
    book,values=rows(export_enterprise_workbook(module,scopes='母公司期末'))
    assert values[-1][1:]==(8,)
    book.close()


def test_export_preserves_large_strings_and_neutralizes_formula_cells():
    module = SimpleNamespace(module_name='主要财务指标', category='indicators', request_params={}, raw_payload={},
        parsed_payload={'periods':['2025年年报'], 'rows':[
            {'key':'x','name':'=HYPERLINK("bad")','unit':'元','values':['900719925474099312345.67']},
        ]})
    book, values = rows(export_enterprise_workbook(module, unit='元'))
    assert values[2] == (1,'=HYPERLINK("bad")（元）','900,719,925,474,099,312,345.67')
    assert book.active['B3'].data_type == 's'
    assert book.active['C3'].data_type == 's'
    book.close()


def test_excel_numeric_cells_keep_underlying_precision_like_source_export():
    module = SimpleNamespace(module_name='主要财务指标',category='indicators',request_params={},raw_payload={},parsed_payload={
        'periods':['2026年中报'],'rows':[{'name':'营业总收入','key':'revenue','unit':'万元','values':['1039981.78']}],
    })
    book, values=rows(export_enterprise_workbook(module,unit='亿元',decimals=2))
    assert values[2][2]==103.998178
    assert book.active['C3'].number_format=='#,##0.00'
    book.close()


def test_excel_precision_guard_does_not_round_before_counting_digits():
    raw='9'*40
    module=SimpleNamespace(module_name='主要财务指标',category='indicators',request_params={},raw_payload={},parsed_payload={
        'periods':['2025年年报'],'rows':[{'name':'金额','key':'value','unit':'元','values':[raw]}],
    })
    book,values=rows(export_enterprise_workbook(module,unit='元'))
    assert isinstance(values[2][2],str)
    assert values[2][2].replace(',','')==raw+'.00'
    book.close()


def test_cash_note_export_keeps_source_numbering_and_numeric_cells_with_disclosed_units():
    module = SimpleNamespace(module_key='cash_notes',module_name='货币资金', category='notes', request_params={}, raw_payload={},
        parsed_payload={'head':['项目名称','现金','银行存款','财务公司存款','其他货币资金','合计'], 'rows':[
            ['20260630','2.87万','15.73亿','','16.57亿','32.29亿'],
            ['20251231','1.83万','7.39亿','','11.80亿','19.19亿'],
        ], 'metadata':{}})
    book, values = rows(export_enterprise_workbook(module))
    assert values == [('数据来源：企业预警通',None,None,None),
                      ('序号','项目名称','2026年中报','2025年年报'),
                      ('1','现金',2.87,1.83),
                      ('2','银行存款',15.73,7.39),
                      ('4','其他货币资金',16.57,11.8),
                      ('5','合计',32.29,19.19)]
    assert book.active['A3'].data_type == 's'
    assert book.active['A3'].number_format == 'General'
    assert book.active['C3'].data_type == 'n'
    assert book.active['C3'].number_format == '###,###,##0.00"万"'
    assert book.active['C4'].data_type == 'n'
    assert book.active['C4'].number_format == '###,###,##0.00"亿"'
    book.close()


def test_inventory_note_export_retains_source_numbers_and_numeric_cells_with_disclosed_units():
    module = SimpleNamespace(module_key='inventory_notes', module_name='存货', category='notes', request_params={}, raw_payload={},
        parsed_payload={'head':['项目名称','原材料','期末余额','采购商品','账面价值合计'], 'rows':[
            ['20260630','7.88亿','7.91亿','','27.06亿'],
            ['20251231','3.23亿','3.26亿','','26.00亿'],
        ], 'metadata':{}})
    book, values = rows(export_enterprise_workbook(module, report='latest,annual'))
    assert values == [('数据来源：企业预警通',None,None,None),
                      ('序号','项目名称','2026年中报','2025年年报'),
                      ('1','原材料',7.88,3.23),
                      ('2','期末余额',7.91,3.26),
                      ('4','账面价值合计',27.06,26)]
    assert book.active['A3'].data_type == 's'
    assert book.active['C3'].data_type == 'n'
    assert book.active['C3'].number_format == '###,###,##0.00"亿"'
    book.close()


def test_finance_cost_note_export_keeps_source_numbering_and_numeric_cells_with_disclosed_units():
    module = SimpleNamespace(module_key='finance_costs', module_name='财务费用', category='notes', request_params={}, raw_payload={},
        parsed_payload={'head':['项目名称','利息支出','减：资本化利息支出','减：利息收入','合计'], 'rows':[
            ['20260630','1.22亿','','-654.91万','1.27亿'],
            ['20251231','2.00亿','','-600.00万','2.06亿'],
        ], 'metadata':{}})
    book, values = rows(export_enterprise_workbook(module, report='latest,annual'))
    assert values == [('数据来源：企业预警通',None,None,None),
                      ('序号','项目名称','2026年中报','2025年年报'),
                      ('1','利息支出',1.22,2),
                      ('3','减：利息收入',-654.91,-600),
                      ('4','合计',1.27,2.06)]
    assert book.active['C3'].data_type == 'n'
    assert book.active['C3'].number_format == '###,###,##0.00"亿"'
    assert book.active['C4'].data_type == 'n'
    assert book.active['C4'].number_format == '###,###,##0.00"万"'
    book.close()


def test_export_keeps_customer_year_groups_and_header_orientation():
    module = SimpleNamespace(module_name='主要销售客户', category='notes', request_params={}, raw_payload={},
        parsed_payload={'head':[['客户名称','第一名','合计']], 'rows':[[['销售额','6.04亿','9.08亿'],['占比','31.30%','47.07%']]],'metadata':{'report':['20251231']}})
    book, values = rows(export_enterprise_workbook(module))
    assert values == [('客户名称','销售额','占比'),('2025年年报',None,None),('第一名','6.04亿','31.30%'),('合计','9.08亿','47.07%')]
    book.close()
