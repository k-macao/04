# 行业附录选择与执行规则

本文件是行业分类的唯一人工可读入口。先定位公司在价值链中的主要利润池，再读取对应附录；不要仅按公司标签或 GICS 名称机械选择。

## 1. 选择协议

1. 按未来 3–5 年价值贡献选择一个主附录，以收入占比、正常化利润、投入资本和估值权重共同判断。
2. 只有当次业务会改变 KPI、现金流模型或估值方法时，才加载一个次附录。
3. 控股公司或三个以上重要分部按 SOTP 拆分；每个分部各用适用附录，集团层面单列净债务、总部费用和交叉持股。
4. 无完全匹配时，选择经济模型最接近的附录，并在报告中写明适配与未覆盖项。
5. 行业附录中的表名、字段名和必写结论句是语义要求。按报告语言完整翻译，不得在英文报告中保留中文模板标签，反之亦然。

## 2. 路由矩阵

| 主附录 | 适用边界 | 主估值方法 | 必备 KPI | 常用次附录 |
|---|---|---|---|---|
| [SaaS](../industries/saas.md) | 订阅或用量制软件 | 反向 DCF、DCF、EV/ARR | NRR/RPO、获客效率、Rule of 40 | 互联网/平台、硬件 |
| [半导体](../industries/semiconductors.md) | 芯片、代工、设备、材料、EDA/IP、封测 | 跨周期 DCF、EV/EBITDA、P/E | 库存周期、ASP/units、良率/利用率 | 硬件、工业 |
| [银行](../industries/banks.md) | 吸收存款并承担信用风险的持牌银行 | 剩余收益、P/TBV-ROTCE | NIM、deposit beta、信用成本、CET1 | 支付/金融科技、资本市场 |
| [保险](../industries/insurance.md) | 财险、寿险、健康险、再保险 | P/B-ROE、P/EV、剩余收益 | combined ratio/VNB、准备金、偿付能力 | 资本市场 |
| [医药](../industries/pharma.md) | 以药品研发和商业化为核心 | 逐资产 rNPV、SOTP | PoS、催化剂、LOE、cash runway | 医疗服务 |
| [医疗服务/器械/CRO-CDMO](../industries/healthcare-services.md) | 医院、诊所、器械、诊断、研发生产外包 | DCF、EV/EBITDA、SOTP | 量/利用率、报销、订单/单位经济 | 医药、工业 |
| [消费](../industries/consumer.md) | 品牌、零售、餐饮、消费品 | DCF、P/E、EV/EBITDA | 量价 mix、同店、sell-through、库存 | 互联网/平台、硬件 |
| [能源](../industries/energy.md) | 上游油气、中游、炼化与综合能源 | 资产 NAV、周期 DCF | 储量/递减、完全成本、套保 | 公用事业、化工型工业 |
| [公用事业](../industries/utilities.md) | 受监管水电气、竞争发电、长期合同基础设施 | rate-base、DDM、DCF | allowed/earned ROE、融资、账单 | 能源、REIT |
| [互联网/平台](../industries/internet-platform.md) | 广告、电商、本地生活、平台型互联网 | 分部 SOTP、DCF | 用户参与、变现率、GMV/take rate | 支付、SaaS、媒体游戏 |
| [支付/金融科技](../industries/payments-fintech.md) | 卡组织、收单、钱包、BNPL、交易平台 | DCF、EV/收入、P/E | TPV、净 take rate、损失 vintage | 银行、资本市场 |
| [资本市场基础设施](../industries/capital-markets.md) | 资管、交易所、券商、评级机构 | DCF、P/E、AUM/交易量驱动 | AUM/净流入或交易量、费率、资本 | 银行、支付 |
| [地产/REIT](../industries/reits.md) | 权益 REIT、mREIT、开发商 | NAV、P/AFFO、DDM | FFO/AFFO、同店 NOI、cap rate、债务墙 | 公用事业、银行 |
| [工业/机械](../industries/industrials.md) | 设备、自动化、航空航天、工程制造 | 中周期 DCF、EV/EBITDA | 订单、book-to-bill、backlog、后市场 | 半导体、硬件 |
| [电信](../industries/telecom.md) | 移动/固网运营商、铁塔、卫星通信 | DCF、SOTP、股息收益率 | ARPU/churn、capex、频谱、股息覆盖 | REIT、媒体 |
| [汽车/EV](../industries/autos-ev.md) | 整车及以整车经济为核心的公司 | 周期 DCF、SOTP | 单车经济、盈亏平衡销量、库存/runway | 硬件、消费 |
| [金属/矿业](../industries/metals-mining.md) | 矿商和勘探开发商 | 分矿山 NAV、期权法 | AISC/成本曲线、储量、矿山寿命 | 工业、能源 |
| [航空/运输](../industries/transport.md) | 航空、机场、铁路、航运、快递物流 | 周期 DCF、NAV、EV/EBITDA | 单位收益/成本、载运率、运力订单簿 | 公用事业、REIT |
| [游戏/媒体/内容 IP](../industries/media-gaming.md) | 游戏、影视、音乐、出版、流媒体、IP 授权 | IP SOTP、DCF、EV/订户 | 用户/受众、付费、内容 ROI、摊销 | 互联网/平台、消费 |
| [硬件/消费电子/AI 服务器](../industries/hardware.md) | 设备、终端、服务器及硬件系统 | 周期 DCF、EV/EBITDA、SOTP | units/ASP/BOM、库存、客户供应商集中 | 半导体、SaaS、工业 |

## 3. 可执行的一手数据入口

以下入口用于快速定位原始数据，具体公司仍以当地监管申报、公司 IR 和定义完整的附注为先。

| 行业 | 官方或一手入口 |
|---|---|
| 通用公司申报 | [SEC EDGAR](https://www.sec.gov/edgar/search/) · [HKEXnews](https://www.hkexnews.hk/) · [巨潮资讯](https://www.cninfo.com.cn/) |
| SaaS / 互联网 / 消费 / 硬件 | 公司 IR 与监管申报；用户或渠道数据只作辅助证据 |
| 半导体 | [WSTS](https://www.wsts.org/) · [SIA](https://www.semiconductors.org/) · [SEMI](https://www.semi.org/en/market-data) |
| 银行 / 支付 | [FDIC BankFind Suite](https://banks.data.fdic.gov/bankfind-suite/) · [FFIEC CDR](https://cdr.ffiec.gov/public/) · [BIS payments](https://www.bis.org/statistics/payment_stats.htm) · [中国人民银行](https://www.pbc.gov.cn/) |
| 保险 | [NAIC](https://content.naic.org/industry/financial-data) · [EIOPA statistics](https://www.eiopa.europa.eu/tools-and-data/insurance-statistics_en) · [国家金融监督管理总局](https://www.nfra.gov.cn/) |
| 医药 / 医疗 | [ClinicalTrials.gov](https://clinicaltrials.gov/) · [FDA databases](https://www.fda.gov/drugs/drug-approvals-and-databases) · [CMS datasets](https://data.cms.gov/) · [NMPA](https://www.nmpa.gov.cn/) |
| 能源 / 公用事业 | [EIA](https://www.eia.gov/) · [FERC eLibrary](https://elibrary.ferc.gov/eLibrary/search) · [NERC](https://www.nerc.com/) |
| 资本市场 | [SEC Investment Adviser Public Disclosure](https://adviserinfo.sec.gov/) · [FINRA statistics](https://www.finra.org/rules-guidance/guidance/reports-studies) · [CFTC market data](https://www.cftc.gov/MarketReports/index.htm) |
| 地产 / REIT | 公司 supplemental packages · [Nareit data](https://www.reit.com/data-research) · 当地土地与不动产登记数据 |
| 电信 | [FCC reports and data](https://www.fcc.gov/reports-research) · [Ofcom data](https://www.ofcom.org.uk/research-and-data/) · [工信部统计](https://www.miit.gov.cn/gxsj/index.html) |
| 汽车 | [NHTSA](https://www.nhtsa.gov/data) · [ACEA](https://www.acea.auto/figure/) · [中国汽车工业协会](https://www.caam.org.cn/) |
| 金属 / 矿业 | [USGS mineral statistics](https://www.usgs.gov/centers/national-minerals-information-center) · [LME market data](https://www.lme.com/en/market-data) · [CME metals](https://www.cmegroup.com/markets/metals.html) |
| 航空 / 运输 | [IATA economics](https://www.iata.org/en/publications/economics/) · [BTS](https://www.bts.gov/) · [中国国家邮政局](https://www.spb.gov.cn/) |
| 游戏 / 媒体 | [Steamworks statistics](https://store.steampowered.com/stats/) · [FCC media data](https://www.fcc.gov/media) · 当地出版、广电、电影监管机构 |

付费数据库或行业媒体可以帮助发现线索，但不得替代可获得的原始来源。每次引用记录 URL、发布日期、数据期间、定义和抓取日期。

## 4. 预测登记与复盘

行业结论必须写成可追踪预测，而不是宽泛观点。每条核心预测至少记录：

| 字段 | 要求 |
|---|---|
| 预测对象 | 明确 KPI、价格、利润率、事件或估值变量 |
| 基准值与截止日 | 写清当前值、期间、来源 |
| 预测区间与期限 | 给区间、方向和明确验证日期 |
| 驱动与先行指标 | 2–4 个可观测变量及阈值 |
| 失效条件 | 上行、下行证伪分别定义 |
| 复盘结果 | 命中/部分命中/未命中/无法验证 |
| 误差归因 | 数据、时间、模型、外生冲击或论点错误 |
| 模型回写 | 调整假设、情景概率或数据源；不得事后改写原预测 |

更新报告时保留旧预测及其时间戳，新增复盘行。股价变化只能作为市场结果之一，不能单独证明经营预测正确或错误；必须分别复盘经营 KPI、催化剂路径、估值倍数和总回报。
