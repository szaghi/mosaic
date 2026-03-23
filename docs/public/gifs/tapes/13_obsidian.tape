Output public/gifs/13_obsidian.gif
Set FontSize 12
Set Width 1200
Set Height 800
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 60s

Sleep 1s

Type "# export results to Obsidian vault"
Enter
Sleep 500ms

Type "mosaic search 'neural scaling laws' -n 3 --oa-only --obsidian --obsidian-folder 'scaling-papers' | slowout 0.1"
Sleep 500ms
Enter
# Hide    # suppress the long network-wait from the recording
Wait    # command still runs to completion
# Show    # reveal terminal with results already present
Sleep 8s
