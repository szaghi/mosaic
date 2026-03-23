Output public/gifs/05_config.gif
Set FontSize 12
Set Width 800
Set Height 1200
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 60s

Sleep 1s

Type "# configuration setup"
Enter
Sleep 500ms

Type "mosaic config --unpaywall-email username@affiliation.xyz"
Sleep 500ms
Enter
Wait
Sleep 1s
Type "mosaic config --show | slowout 0.15"
Enter
Wait
Sleep 2s
