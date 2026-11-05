"""A prewritten, reproducible reading sample; never calls a model or the network."""
from . import ladder, local, store

SECTIONS = [
    ("先看地图，再进入细节", "先看全貌", [
        ("读长文最困难的，往往不是理解某一句话，而是不知道它在整篇文章中的位置。我们在段落之间来回跳转，一边读新内容，一边努力记住已经读过的观点。先看到文章的结构，可以帮助我们决定从哪里开始，以及哪里值得慢下来。", "先了解文章结构，再决定阅读顺序", "结构帮助读者判断段落的位置和重要性", "文章结构"),
        ("TextFold 把同一篇文章放在五个信息层级中：全文、简述、关键句、要点和主题。主题层展示章节地图；展开一个感兴趣的部分，就能逐步看到支撑结论的理由和原句。层级改变的是眼前的信息密度，原文仍然可以随时找回。", "五个层级让文章从章节地图逐步展开到原文", "每一层都指向同一份文档，便于随时核对", "五个层级"),
    ]),
    ("让每个结论都有回去的路", "回到原文", [
        ("压缩后的文字容易阅读，也可能省略条件、例外和不确定性。看到一个重要结论时，我们需要知道它依赖哪些原句，而不仅仅是得到一个听起来合理的概括。折叠阅读因此保留了从简短表达回到原段落的路径。", "重要结论需要能够回到支撑它的原句", "条件和例外可能在压缩时被省略，需要阅读者核对", "原句依据"),
        ("简述层保留选出的原句，其他紧凑层级可以由模型重新表达。读者可以在全文中检查措辞、数字和前提，再决定是否接受一个概括。这份内置示例的折叠层级是预先编写的，用来演示交互，不代表系统已经为你的文档调用了模型。", "区分原句与改写，才能判断概括是否可靠", "本示例预先编写，真实文档需要连接模型生成 AI 层级", "核对概括"),
    ]),
    ("在浏览器里完成一次阅读", "浏览器阅读", [
        ("打开网页后，可以粘贴链接、上传含文字的 PDF 或 Word，也可以直接粘贴正文。文章和笔记保存在运行服务的数据目录中，刷新网页后仍然存在。阅读器沿用原项目的缩放、原文对照、标注和导出方式。", "链接、文件和正文都可以成为浏览器里的阅读材料", "服务保存文档与笔记，让阅读可以在下次继续", "导入材料"),
        ("试着按键盘上的 1 到 5，观察信息从全文收拢到主题。也可以拖动下方的缩放条，或者点击某一段，只展开你想深入理解的内容。选中文字后可以高亮或写笔记，保存时可以选择导出当前层级。", "按 1 到 5 或拖动缩放条，选择适合当前任务的信息密度", "局部展开、标注和导出帮助保留自己的阅读线索", "缩放阅读"),
    ]),
]

TEXT = "# TextFold 网页阅读指南\n\n" + "\n\n".join(
    "## " + title + "\n\n" + "\n\n".join(p[0] for p in paragraphs)
    for title, _, paragraphs in SECTIONS
)
DEMO_ID = local.make_id("TextFold 网页阅读指南", TEXT)


def ensure_sample():
    """Create once; preserve notes and changes on subsequent launches."""
    if store.has(DEMO_ID):
        return DEMO_ID
    pid = local.import_text(TEXT, "web-reading-guide.md")
    doc = store.parsed(pid)
    doc["meta"]["lang"] = "zh"
    if len(doc["chunks"]) != len(SECTIONS) or any(
        len(chunk["units"]) != len(section[2]) for chunk, section in zip(doc["chunks"], SECTIONS)
    ):
        raise ValueError("The sample's parsed sections no longer match its prewritten levels")
    for chunk, (title, topic, paragraphs) in zip(doc["chunks"], SECTIONS):
        chunk["lad"] = ladder.section_ladder({"takeaway": paragraphs[0][1], "topic": topic}, doc=doc, chunk=chunk)
        for uid, (_, takeaway, reason, unit_topic) in zip(chunk["units"], paragraphs):
            u = doc["units"][uid]
            u["lad"] = ladder.assemble(u, {"evidence": [0], "takeaway": takeaway, "reason": reason, "topic": unit_topic}, doc["atoms"], "prewritten-web-sample", True)
    store.save_en(doc, "prewritten-web-sample")
    return pid
