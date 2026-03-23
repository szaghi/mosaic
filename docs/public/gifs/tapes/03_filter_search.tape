Output public/gifs/03_filter_search.gif
Set FontSize 12
Set Width 1100
Set Height 500
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 60s

Sleep 1s

Type "# search with multi-filter on specific source"
Enter
Sleep 500ms

Type "mosaic search 'hypersonic high order simulation' -y 2022-2024 --source sp -n 5"
Sleep 500ms
Enter
Hide    # suppress the long network-wait from the recording
Wait    # command still runs to completion
Show    # reveal terminal with results already present
Sleep 8s
