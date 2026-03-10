Output public/gifs/07_notebook.gif
Set FontSize 14
Set Width 1100
Set Height 600
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 180s

Sleep 1s
Type "# First-time: authenticate with your Google account"
Enter
Sleep 500ms
Type "notebooklm login"
Sleep 500ms
Enter
Wait
Sleep 2s
Type "# Then create a notebook from a search in one command:"
Enter
Sleep 500ms
Type "mosaic notebook create Transformers --query 'attention is all you need' --oa-only --podcast"
Sleep 500ms
Enter
Wait
Sleep 4s
