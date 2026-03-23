Output public/gifs/02_search_download.gif
Set FontSize 12
Set Width 1200
Set Height 800
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 120s

Sleep 1s

Type "# search and download open-access only"
Enter
Sleep 500ms

Type "mosaic search 'mhd amr solver' --oa-only --download -n 1"
Sleep 500ms
Enter
Hide    # suppress the long network-wait from the recording
Wait    # command still runs to completion
Show    # reveal terminal with results already present
Sleep 6s
