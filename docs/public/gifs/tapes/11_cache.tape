Output public/gifs/11_cache.gif
Set FontSize 12
Set Width 1000
Set Height 600
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 60s

Sleep 1s

Type "# cache statistics"
Enter
Sleep 500ms

Type "mosaic cache stats | slowout 0.1"
Sleep 500ms
Enter
Wait
Sleep 2s

Type "# list recently cached papers"
Enter
Sleep 500ms

Type "mosaic cache list -n 5 | slowout 0.1"
Sleep 500ms
Enter
Wait
Sleep 3s

Type "# bulk export cached papers to BibTeX | slowout 0.1"
Enter
Sleep 500ms

Type "mosaic cache export cached.bib -n 10 | slowout 0.1"
Sleep 500ms
Enter
Wait
Sleep 2s
