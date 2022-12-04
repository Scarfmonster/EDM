# Enunu Database Maker
Absolutely not named because the abbreviation was amusing.

A script I made because at some point I got fed up with repeating the same actions when editing LABs and testing VBs. Currently only works with Japanese. In some vague future I plan to update it to support more languages in the same way lab2ust does.

Initially started as an edit of UtaUtaUtaus lab2ust plugin to allow running it outside UTAU in a more automated way.
At some point I removed the requirement of manually creating the FRQ files and then decided it may as well create a convenient 7z file as well.
It also does some rudimentary checks. If it refuses to generate the 7z archive, the DB WILL break during the training. If you use vlabeler it will try to give you the specific phoneme number it thinks is wrong.

## USAGE
It expects the same folder structure as enunu.

It was designed for fast prototyping, so it will always overwrite the ust files in the UST folder. Depending on how stable your singing is, manually editing USTs may not even be necessary. FRQ files are not needed and not used.

You may want to edit the short configuration inside makedb.py. And definitely should edit db_name to something more useful.
If for whetever reason a song shouldn't be used when creating a DB, simply comment out it's tempo entry in tempos.txt.

## Thanks
It's derived from UtaUtaUtaus lab2ust found at https://github.com/UtaUtaUtau/nnsvslabeling
It also uses pyUtau, with a few minor edits, found at https://github.com/UtaUtaUtau/pyUtau
