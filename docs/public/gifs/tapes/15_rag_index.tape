Output public/gifs/15_rag_index.gif
Set FontSize 12
Set Width 1100
Set Height 600
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 300s

Sleep 1s

Type "# check embedding model configured for local RAG"
Enter
Sleep 500ms

Type "mosaic config --show"
Sleep 500ms
Enter
Wait
Sleep 2s

Type "# index all cached Maxwell / high-order EM papers"
Enter
Sleep 500ms

Type "mosaic index"
Sleep 500ms
Enter
Hide    # suppress embedding API wait (local qwen3-embedding:8b)
Wait
Show
Sleep 4s

Type "# force a full re-index (after switching embedding model)"
Enter
Sleep 500ms

Type "mosaic index --reindex"
Sleep 500ms
Enter
Hide
Wait
Show
Sleep 3s
