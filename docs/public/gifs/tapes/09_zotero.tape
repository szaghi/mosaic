Output public/gifs/09_zotero.gif
Set FontSize 12
Set Width 1200
Set Height 900
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 60s

Sleep 1s

Type "# zotero integration"
Enter
Sleep 500ms

Type "mosaic search 'adaptive mesh refinement cfd gpu' --oa-only --sort citations --zotero --zotero-collection 'amr-cfd-gpu'"
Sleep 500ms
Enter
Hide    # suppress the long network-wait from the recording
Wait    # command still runs to completion
Show    # reveal terminal with results already present
Sleep 8s
