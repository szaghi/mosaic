Output public/gifs/16_rag_ask.gif
Set FontSize 12
Set Width 1200
Set Height 900
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 300s

Sleep 1s

Type "# RAG synthesis — state of the art on high-order FDTD"
Enter
Sleep 500ms

Type "mosaic ask 'high-order FDTD methods for Maxwell equations' --show-sources | slowout 0.1"
Sleep 500ms
Enter
Wait
Sleep 6s

Type "# gap analysis — what open problems remain?"
Enter
Sleep 500ms

Type "mosaic ask 'adaptive mesh refinement grids for Maxwell equations' --mode gaps | slowout 0.1"
Sleep 500ms
Enter
Wait
Sleep 6s

Type "# save the answer to a Markdown file"
Enter
Sleep 500ms

Type "mosaic ask 'staggered vs amr grid schemes for Maxwell equations' --mode compare -o maxwell_compare.md"
Sleep 500ms
Enter
Wait
Sleep 3s
