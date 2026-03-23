Output public/gifs/10_similar.gif
Set FontSize 12
Set Width 1200
Set Height 400
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 60s

Sleep 1s

Type "# find papers similar to 'Attention is All You Need'"
Enter
Sleep 500ms

Type "mosaic similar 10.48550/arXiv.1706.03762 -n 5 --sort citations"
Sleep 500ms
Enter
Hide    # suppress the long network-wait from the recording
Wait    # command still runs to completion
Show    # reveal terminal with results already present
Sleep 8s
