# A hand-off: mosaic opens the article in your browser and files the PDF you download.
# Recorded without a browser: BROWSER=true stands in for it, and a background copy for your click on
# "Download PDF", six seconds later (make_gifs.sh sets both up).
Output public/gifs/handoff.gif
Set Height 380
Source tapes/_setup.tape

Hide
Type `( (sleep 6; cp "$MOSAIC_GIF_PDF" ~/Downloads/1-s2.0-S0376042106000029-main.pdf) & ) && clear`
Enter
Show

Type 'mosaic get 10.1016/j.paerosci.2006.01.001 --handoff'
Sleep 400ms
Enter
Wait@90s
Sleep 6s
