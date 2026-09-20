# 拼豆图纸工具用户真实抱怨调研（原始报告 B）

来源：中国区 App Store 14 款拼豆 App 共 1356 条评论（筛出 261 条算法/质量相关）、V2EX、linux.do、GitHub issues、百度贴吧、微博、B 站、Reddit（r/PerlerBeads、r/beadsprites、r/PixelArt、r/CrossStitch、r/diamondpainting，经归档镜像）、海外 App Store、PCStitch 论坛、十字绣/钻石画工具文档。
未获取：小红书、知乎站内、豆瓣、B 站评论区、Google Play。注意：搜索引擎上大量"横评/避坑"文是厂商 SEO 软文，仅用于佐证真实用户已提到的痛点（标【厂商文】）。
标注：[多人] = 多个独立来源反复出现；[个别] = 单一来源。

## 1. 像素化 / 图纸质量

### 1.1 "要么颜色乱成一团，要么糊成一坨"——尺寸与细节两难 [多人，最高频]
- Reddit r/PerlerBeads (u/Material-Wrongdoer79)："The results are either a giant, noisy mess with way too many colors, or they're so simplified they look like a blurry blob and lose all their personality." reddit.com/r/PerlerBeads/comments/1m631fv/
- App Store《拼豆图纸生成器》1★："生成的一点都不像10分之一都没有"；"生成的就是马赛克生成器"
- App Store《拼豆绘》1★："充完发现生成的图纸分辩率超低…一塌糊涂"
- App Store Perlypop 2★："I put in the simplest flat color cartoon drawings and it can't make a clear image at all."（29×29 板）
- B 站 BV1p3raB8EMh 评论（432 赞）："市面上9成9的所谓像素ai其实就是搞成右边这样"（纯降分辨率打码）
- 开发者视角（linux.do, liangdabiao）："能不能在1000-3000颗粒就能够展示出很好的效果" linux.do/t/topic/1660924

### 1.2 杂色/散点 [多人]
- CSDN（bitbead 作者转述）："一大片肤色里飘着 3 颗浅紫、2 颗橄榄绿、1 颗砖红…为这几颗专门下一单?运费都比豆贵。不买?图纸对不上…大部分「照片转拼豆」工具根本没管这件事" blog.csdn.net/wendongfeng/article/details/162612547
- B 站 BV193aEz6EV4 评论："明明已经合并了颜色，为啥还是一堆颜色的呢?"
- B 站 BV14p5jzkEYK："特殊色出现太多了…希望能把范围限定在常用色"
- Reddit（u/lizard_e_）："I find cleaning up by hand to be a mandatory step."
- 微博 #拼豆体验分享#："图纸颜色又多又乱拼的我好懵啊！" weibo.com/2/detail/5333349558390492
- Zippland #1 去杂色恢复颜色不对 github.com/Zippland/perler-beads/issues/1

### 1.3 随机加入原图没有的颜色 / 灰色毛边 [多人]
- Reddit (u/Limp_Isopod_3121)："A lot of the websites I search up adds random colors that does not fit" reddit.com/r/PerlerBeads/comments/1rl1jf1/
- Reddit (u/Consistent_Tomato138, Perlypop)："I've definitely been noticing it adding random colors more often than not"
- perler-beads-ai README："颜色识别不准确、灰色毛状边界线、无法自适应合并同色系"——"黑色毛边是因为池化过程中对RGB采用了mean操作"
- r/CrossStitch (u/NevaSirenda)："the computer 'sees' colors that aren't really there" reddit.com/r/CrossStitch/comments/o0fysd/

### 1.4 纯色块被吃掉只剩轮廓 [个别但具体]
- V2EX 试用 PindouAI（XhivaW）："底色上的纯色色块被完全忽略了，只保留边缘的一圈" v2ex.com/t/1220906

### 1.5 眼睛/高光/人脸不像 [多人]
- App Store《拼豆图纸生成器》2★："眼睛根本不对称，眼睛的白色高光点也不对"
- r/CrossStitch 设计师 u/Ko_Mari："it's best to test the eye and the skin around it… If you get a blurry spot with a lot of confetti, better not to cross stitch." reddit.com/r/CrossStitch/comments/14mmmy1/
- Reddit (u/poisonheml0ck)："the conversion left out details that our brains will naturally pick up" reddit.com/r/PerlerBeads/comments/1w7k215/

### 1.6 格数/板子尺寸选不好、图纸不匹配板子 [多人]
- Reddit (u/MammothStrain2426)："it never has the proper grid for my boards." reddit.com/r/PerlerBeads/comments/1uega5x/
- B 站评论（pindoupic）："没法选择长宽，只能做正方形的"
- beadifier #113："arbitrarily constrained by the board dimensions"
- BeadInventory PR #98：只有六种规格，"选不到自己那块的人只能挑一个「差不多大」的，孔对不上"
- 贴吧："软件要求图片像素不超过500*500"

### 1.7 非正方形原图被拉伸变形 [个别，厂商文]

## 2. 色号匹配

### 2.1 色号与实物不符（App Store 差评第一大类） [多人]
- 《我嘞个豆》1★："拼豆颜色识别不对 害的我豆都扔了"；"明明是两个颜色识别成了一个颜色！全部拼错！"；"一个色号里面有十多个颜色堆在一起"
- 《拼豆猫》2★："鹅黄色识别为绿色？？？？"
- 《拼豆画》1★："色号色差都变了，脸都变成绿色的了…越更新色号色差越大"
- 《像素星球》2★："效果图同色号的豆颜色不一样"
- 《豆纸》1★："色号解析非常不准确"；2★："大图识别有几乎一半的颜色都识别不到"
- V2EX："灰色的键帽都被识别成紫色了"
- r/beadsprites："the compression color algorithm tends to not fixate the outline with H7 black" reddit.com/r/beadsprites/comments/1vqe5rd/
- Reddit 自研者归纳："dark colors drifted to pure black, or pale colors just became washed out white" reddit.com/r/PerlerBeads/comments/1skri6d/
- beadifier #61："the Delta E color matching makes weird calls sometimes"

### 2.2 色卡来源不明 / 官方无色值 / 品牌不全 [多人]
- Zippland #2："色号RGB值有出处嘛，还是自己调试的"（无人回答）
- Dotsy 作者："bead makers don't publish official color values, palettes come from community lists."
- 《我嘞个豆》3★："什么时候可以出星芒的色号"；B 站："我只有mard常规221色，能只选到221色吗"
- 《像素星球》4★："我的豆子只有72色…不是所有人都有全套颜色"
- beadifier #40 mini/midi 混淆、#29 推荐停产色 H25

### 2.3 相近色太多 / 无法手动合并 [多人]
- 《豆纸》3★："一模一样的色号总是会识别成好几个，希望可以手动合并"
- 《拼豆图纸生成器-拼豆助手》1★："不支持设置颜色数量，经常出现不常用颜色！图纸不支持修改"

### 2.4 屏幕预览 vs 实物色差 / 肤色 [多人]
- 《我嘞个豆》3★："颜色跟实际的豆子会有一点点色差…图纸跟实物不太一样"
- 《颂拼豆》5★建议："自定义色号十六进制值（有些色号色差有点大）"
- r/CrossStitch（Pic2Pat 转猫）："very dull and uses a lot of greens rather than greys"

## 3. AI 重绘 / AI 出图

### 3.1 AI 直出的"拼豆图"不是网格：伪像素、半颗豆、豆子中途换色 [多人，情绪最强]
- B 站 BV193aEz6EV4《AI像素画三大天坑》：伪像素网格（大小不一互相挤压）、色彩污染（纯黑轮廓塞进十几种灰黑）、边缘柔化抗锯齿（半透明柔化色="不存在的颜色"）
- perfectPixel issues：#14 清晰原图误判成 22×22；#8 png 透明像素变黑 github.com/theamusing/perfectPixel/issues
- Reddit (u/Opening-Ear-7825)："I absolutely CANNOT get ChatGPT to make a bead pattern correctly. The grid is always messed up." reddit.com/r/PerlerBeads/comments/1w9orck/
- r/beadsprites："the AI doesn't understand perler beads… put dots of color inside other beads"；"using half and quarter beads" reddit.com/r/beadsprites/comments/1krgeld/
- r/PerlerBeads 522 赞帖："Full of AI images that 'look right' at first glance but could never be made in reality."；"beads randomly switching colour halfway through the bead" reddit.com/r/PerlerBeads/comments/1vf0756/
- r/PixelArt AI 特征："Mixels… unrestricted color palette, gradient without dithering"

### 3.2 AI 结果两极分化、色号全错、细节数错 [多人]
- 微博 #豆包 拼豆图纸#："实际拼出来的效果评价两极分化" weibo.com/2/detail/5330409848048777
- baijiahao："AI生成的CSGO钥匙图纸色号全错…AI把钥匙齿牙数错了，少了一格"；"店主直接用AI跑图，色号和图纸严重不符"

### 3.3 AI 重绘改掉细节 → 不像本人 [多人]
- MeltDots 作者自述："It may redraw details, so compare the result with your original."
- PixelMe 2★："a picture of Vaporeon and it made them a person"

### 3.4 社区对"AI"标签的抵触，但对算法转换不反感 [多人]
- "does anyone know any websites… that arent ai?" reddit.com/r/PerlerBeads/comments/1tgb5ax/
- "There are plenty of tools, including photoshop, that convert regular photos into pixelated art. And these tools aren't necessarily 'using AI.'"（12 赞）

## 4. 可拼性

### 4.1 悬空/细部一熨就塌或断 [多人]
- baijiahao："头发尖、花瓣末梢悬空只靠一点连主板…熨斗一压直接瘫平"；"老手两个解法：空隙塞透明（Clear）豆当桥，或用H1特殊烫" baijiahao.baidu.com/s?id=1869813538010679620
- baijiahao《发尾空隙不补H1必塌房》："H1透明豆在发尾空隙里充当骨架"
- Reddit (u/UpstairsAway)："watch out for single-bead strays set at an angle that won't melt to anything else"
- Reddit (u/camomcg)："one of the legs (only 3-5 beads wide) was an obvious atrocity"
- smzdm："MARD 熔点比 Perler 低，中温档多停三五秒细部直接化没影"

### 4.2 一格间隙是熨烫连片的底线 [个别但实测]
- BeadInventory PR #72："一格是烫豆子的底线（挨着的豆子烫完连成一片）"

### 4.3 出图超板 / 多板拼接错位 [多人]
- Reddit 396 赞 (u/helpivebeenhexxed)："had to buy more boards… they didn't fit together, there's a visible line" reddit.com/r/PerlerBeads/comments/1g3n3f9/
- 店主："avoid interlocking multiple 52x52 boards, height differences at the seams"
- 【厂商文】"分块切在了像素半格上"
- 《颂拼豆》5★："400×200格的图保存只显示一部分，分开保存就闪退"
- 翘边："越大的图越容易翘边"（B 站视频简介）

### 4.4 板数/尺寸设定后不可改（Kandipad） [个别]

## 5. 导出与实操

### 5.1 打印尺寸对不上板子 [多人]
- 《perler拼豆图纸生成器》1★："打印出来的图纸和实际大小严重不符"
- Reddit："it never lines up"（垫板打印）；"It's too finicky to have it under the board"

### 5.2 色号/网格看不清、数格子出错 [多人]
- 《豆画》5★建议："板子10格一划分5格标虚线，8*8的分格对不上"
- 《豆纸》3★："网格跟图纸对不上，微调不懂调哪条线"；"已完成色号默认黑色不显示原色更眼花"
- B 站："色编号最好不顶到格子上，两边编号都连上了很混乱"
- Zippland #20：想隐藏 T01 白格数字
- BeadInventory PR #101："线没落在像素上…1pt 线被抗锯齿摊到两三个像素，屏幕上是一层灰雾"
- Reddit：圆珠图线太细；黑白打印无图例

### 5.3 材料清单 / 用量统计 [多人]
- 《我嘞个豆》："经常加载不出来豆子数量"；"数量多的色号最后几排空白"
- Reddit："Is there an app that would tell me '3,000 black, 200 yellow, 34 red'? I've tried chat gpt, was a big fail." reddit.com/r/PerlerBeads/comments/1qk2x3u/
- bitbead：清理后"28 种色号→15 种，购物清单砍一半"
- 十字绣同类（327 赞）："the pattern assumes a skein is 100 cm whereas DMC is 800 cm!"

### 5.4 背景/透明处理 [多人]
- Reddit："generators keep adding it (background), messes up the pattern" reddit.com/r/PerlerBeads/comments/1j3jji9/
- 《像素星球》：想要透明底 PNG 导出；Perlypop："eliminate background on transparent image"
- Zippland #13 透明→白；perfectPixel #8 透明→黑
- 《我嘞个豆》："有一些水印它会识别上去"

### 5.5 生成后不可编辑 / 编辑效率低 [多人]
- 《拼豆图纸生成器-拼豆助手》1★："生成的图纸不支持修改"
- Zippland #3：要连续填色/油漆桶
- 《我嘞个豆》："人工筛取颜色可以滑动选取！手要点抽筋了"；《拼豆绘》："没法吸色号很鸡肋"
- 【厂商文】"一张不能编辑的图纸，就像一张'死图'"

## 6. 具体产品评价（摘）
- 拼豆图纸生成器（涛张 iOS，1.1 万评分）：刷 20 字好评换免费导出；真实负评"一点都不像""马赛克生成器"
- 我嘞个豆：识别准确率最集中差评；大图闪退
- 拼豆画：脸变绿、越更新色差越大；拼豆绘：扣费投诉为主
- 颂拼豆："图纸根本不能用就是一坨"；大图导出崩溃
- 拼豆咔 / 一豆成画 / 刀盾拼豆 / MakeBead / BeadFuse / Fotor：**未找到独立真实用户评价**（仅厂商自述与软文）
- Perlypop（海外口碑第一）：random colors、29×29 不清晰、96% 功能在 £19 订阅墙后
- Beadifier：停产色、mini/midi 混淆、ΔE 判断怪、大板崩溃
- ChatGPT/Gemini 直出：网格必乱、"can't count cells"

## 7. 跨领域启发：十字绣/钻石画已解决、拼豆未普及
| 拼豆抱怨 | 十字绣/钻石画解法 | 来源 |
|---|---|---|
| 散点手工清理 | 8 邻域投票多轮平滑 + 可调强度 + before/after 统计 + **遮罩保护眼睛高光** + 散点热图 ConfettiScope | Xstitchify、Stitchmate |
| 几颗的色号 | 按用量阈值剔除（N=3~10 针）；减色要同时看色距和使用量（PCStitch 2008 年就被骂只看色距） | pcstitch.com/forums TOPIC_ID=532 |
| 卡通照片同一套量化 | photo / clip art 两种导入模式：clip art 关抖动直接吸原色 | WinStitch |
| 先量化再缩放糊 | 先缩到 1:1 格数再量化 | r/CrossStitch g9agcn |
| 轮廓丢失黑线变杂灰 | **描边独立图层**（backstitch layer），色块与黑线分层 | FlossCross、WinStitch、KGChart |
| 尺寸不知选多大 | **尺寸推荐器**：每尺寸给推荐/最小可接受/质量分 + 预览哪些细节会丢；卖家硬规则：单人脸 ≥64×80 格、脸占画面一半以上 | diamondpaintingconverter.com |
| 文字看不清 | "preview 里勉强能读 = 成品读不了"，建议粗体点阵字体 | r/diamondpainting |
| 相近色号符号难分 | 符号可读性规则：禁近似符号组、相近色不给相近符号、色块+符号双编码 | ursasoftware.com/macstitch |
| 大图分页对不齐 | 分页带重叠区与板号、四角对位标记 | r/CrossStitch |
| 死图不能改 | 原图半透明叠底 + 区域批量替换 + 画笔/填充/吸管，"没有转换器能免修" | PCStitch underlay |
| 暗部眼睛丢 | 预处理建议：提对比、暗部提亮；"cartoon 图要 target exactly those colors" | r/CrossStitch |
| 近看怪 | "退远看"缩略模拟预览 | r/CrossStitch rcwhmr |

**拼豆特有、两领域都没解决**：
1. 可拼性/结构校验（悬空、单颗斜连、1 格宽细线熨烫会塌）——社区解法"补透明豆 H1 当桥"，工具可自动检测并建议补透明豆或加粗到 ≥2 格
2. AI 出图网格对齐（perfectPixel 路线有效但清晰原图会误判）
3. 品牌色卡真值：厂商不公布色值，所有工具都是社区/淘宝抄的——比算法本身更重要

## 8. 频次汇总
多人（≥4 独立来源）：① 色号匹配与实物不符 ② 杂色/散点与几颗色号 ③ 尺寸两难与板子不匹配 ④ AI 网格不对齐/半颗豆/中途换色 ⑤ 随机新颜色/灰毛边 ⑥ 打印比例对不上 ⑦ 品牌色卡不全/无法只用自己有的色 ⑧ 悬空细部熨塌 ⑨ 不可编辑 ⑩ 色号网格看不清
个别（可直接转测试用例）：纯色块被吃、灰键帽→紫、鹅黄→绿、脸变绿、透明变黑/白、非方图拉伸、水印入图、8×8 分格与板刻度错位、编号顶格粘连
