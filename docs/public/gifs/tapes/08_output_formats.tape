Output public/gifs/08_output_formats.gif
Set FontSize 12
Set Width 1200
Set Height 1000
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 60s

Sleep 1s

Type "# output formats"
Enter
Sleep 500ms

Type "mosaic search 'maxwell pic conservative high order' -n 1 --output results.bib --output results.csv --output results.md"
Sleep 500ms
Enter
Hide    # suppress the long network-wait from the recording
Wait    # command still runs to completion
Show    # reveal terminal with results already present
Sleep 5s
Type "head -50 results.bib | slowout 0.1"
Enter
Wait
Sleep 5s
Type "head -50 results.md | slowout 0.1"
Enter
Wait
Sleep 5s
