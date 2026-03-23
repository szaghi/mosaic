Output public/gifs/06_auth_status.gif
Set FontSize 12
Set Width 1100
Set Height 400
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 10s

Sleep 1s

Type "# auth status"
Enter
Sleep 500ms

Type "mosaic auth status"
Sleep 500ms
Enter
Wait
Sleep 2s
Type "# Log in to a publisher site (opens headed browser):"
Sleep 1s
Type ""
Enter
Sleep 500ms
Type "mosaic auth login elsevier --url https://www.sciencedirect.com"
Sleep 2s
Enter
Sleep 8s
