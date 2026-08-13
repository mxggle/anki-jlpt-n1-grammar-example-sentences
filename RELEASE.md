# 发布流程

版本号、Anki 牌组说明、AnkiWeb 说明和 `.apkg` 必须在同一次发布中同步更新。

## 1. 修改与对账

1. 以 `shin-kanzen-n1-grammar/notes.csv` 为卡片内容的唯一事实来源。
2. 以 `(课号, 课内序号)` 为稳定键；不要只用语法名称匹配卡片。
3. 教材 OCR 校订先运行 dry-run，再使用 `--apply`；不确定内容写入 `reconciliation/questions.md`，不要猜测。
4. 日文原句变更后，中文翻译、详细解析和音频都必须复核。

## 2. 重新生成音频

先启动本机 VOICEVOX Engine（默认 `http://127.0.0.1:50021`），确认 FFmpeg 位于 `/opt/homebrew/bin/ffmpeg`，再执行：

```bash
python3 scripts/gen_audio_voicevox.py --dry-run
python3 scripts/gen_audio_voicevox.py --speaker 23 --workers 4
```

脚本会覆盖 `shin-kanzen-n1-grammar/medias/` 中与卡片对应的 MP3。生成失败时退出码非零，不得继续发布。

## 3. 更新版本与说明

1. 按语义化版本修改 `VERSION`。
2. 在 `CHANGELOG.md` 顶部添加带日期的版本记录。
3. 同步更新 `ankiweb-description-simple.html` 和 `ankiweb-description.html`。
4. 运行 `python3 scripts/verify_release.py`，版本或统计不一致时不得发布。

## 4. 构建并验证 `.apkg`

```bash
python3 scripts/build_apkg.py dist/JLPT_N1_N1__-v$(cat VERSION).apkg
python3 scripts/verify_release.py --apkg dist/JLPT_N1_N1__-v$(cat VERSION).apkg
```

构建会保留既有 note GUID、card ID 和 deck ID，只更新内容、模板、样式、媒体与包内牌组说明。发布前保留旧 `.apkg` 作为回滚备份。

## 5. 在 Anki 中同步说明

`.apkg` 导入器不保证覆盖用户本地已存在牌组的 `Description`。维护者必须在 Anki 中打开顶层牌组的 Options/Description，将 `ankiweb-description-simple.html` 的内容粘贴进去并保存，然后重新打开 Description 检查版本号。

## 6. 最终检查

- `python3 scripts/validate_reconciliation.py` 通过。
- `python3 scripts/verify_release.py --apkg ...` 通过。
- Anki 中显示的版本与 `VERSION` 相同。
- 随机抽查至少 3 课的正面、背面、高亮、中文解释和音频。
- Git diff 中没有密钥、临时文件、构建缓存或意外的大文件。
- 发布 Release、更新 AnkiWeb 后，再从下载页做一次干净导入测试。
