# notes.csv 字段映射

`notes.csv` 没有表头，前四行是 Anki 导入指令。数据从第 5 行开始，每行固定 22 列。

| 列 | 推断字段 | 对账策略 |
|---:|---|---|
| 1 | Deck | 保持旧牌组结构 |
| 2 | FrontSentence | 从书页 cloze 重建 |
| 3 | GrammarPattern | 使用书页语法标题 |
| 4 | LessonInfo | 稳定主键：`第N課 - M` |
| 5 | BackSentence | 从书页 cloze 重建高亮 |
| 6 | Reading | 当前全空；`n1-ocr` 无振假名数据 |
| 7 | Translation | 不自动覆盖，需人工翻译复核 |
| 8 | AudioFile | 保留文件名；原句变化时标记试听/重录 |
| 9–10 | GrammarFormation | 使用书页接续栏 |
| 11 | StyleNotes | 保持旧值 |
| 12 | ExplanationJapanese | 使用书页意义栏 |
| 13–15 | 中/英派生释义 | 不自动覆盖 |
| 16 | AdditionalNotes | 使用书页注意栏 |
| 17 | AdditionalNotesZh | 不自动覆盖 |
| 18 | 预留 | 当前全空 |
| 19 | DetailedExplanation | 只同步开头的日文例句；生成正文需人工复核 |
| 20 | Lesson/tag 辅助值 | 保持旧值 |
| 21 | 全局序号 | 保持旧值 |
| 22 | Tags | 当前全空 |

逐卡身份使用 `(LessonInfo, 课内序号)`，再以同课语法分组与句子相似度校验。不能只用语法名，因为 `～をもって` 跨第2课和第11课重复。
