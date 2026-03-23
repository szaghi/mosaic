Output public/gifs/01_quick_search.gif
Set FontSize 12
Set Width 1200
Set Height 1100
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 60s

Sleep 1s

Type "# simple search on all enabled sources"
Enter
Sleep 500ms

Type "mosaic search 'scramjet high order simulation' --max 1"
Sleep 500ms
Enter
Hide    # suppress the long network-wait from the recording
Wait    # command still runs to completion
Show    # reveal terminal with results already present
Sleep 6s
