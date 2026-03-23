Output public/gifs/04_doi_get.gif
Set FontSize 12
Set Width 1100
Set Height 200
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 60s

Sleep 1s

Type "# fetch a single paper by DOI"
Enter
Sleep 500ms

Type "mosaic get 10.48550/arXiv.1706.03762"
Sleep 500ms
Enter
Hide    # suppress the long network-wait from the recording
Wait    # command still runs to completion
Show    # reveal terminal with results already present
Sleep 8s
