Output public/gifs/14_cached_search.gif
Set FontSize 12
Set Width 1200
Set Height 600
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 60s

Sleep 1s

Type "# search the local cache (no network)"
Enter
Sleep 500ms

Type "mosaic search 'transformer' --cached -n 5 | slowout 0.1"
Sleep 500ms
Enter
Wait
Sleep 5s
