Output public/gifs/12_bulk_get.gif
Set FontSize 12
Set Width 1100
Set Height 300
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 120s

Sleep 1s

Type "# create a small .bib file with a couple of DOIs"
Enter
Sleep 500ms

Type "printf '@article{a,doi={10.48550/arXiv.1706.03762}}\n@article{b,doi={10.48550/arXiv.2005.14165}}\n' > sample.bib"
Sleep 500ms
Enter
Wait
Sleep 500ms

Type "# bulk-download open-access PDFs for every DOI in sample.bib"
Enter
Sleep 500ms

Type "mosaic get --from sample.bib --oa-only"
Sleep 500ms
Enter
Hide    # suppress the long network-wait from the recording
Wait    # command still runs to completion
Show    # reveal terminal with results already present
Sleep 6s
