# Clegg references: Zotero changes and open points

Checked against Clegg's own reference list (Frameworks of Power, SAGE back matter, 436 references).
Changed items carry the tags `clegg-ids-added` (DOIs/ISBNs) and `clegg-fix-applied` (corrections);
new records carry `added-from-clegg-bibliography`. Earlier values: `zotero_backup_before_write.json`.

## Done
- **Added 10 references missing from the collection:** Lukes 1974 (Power: A Radical View), 1976 (Reply to Bradshaw), 1977 (Essays in Social Theory), 1982 (Of Gods and Demons); Locke 1959; Lockwood 1964; Ball 1978 and 1988; Littler & Salaman 1982; Benton 1977.
- **Bare PDFs given parent records:** the Benton preview PDF (J6BEHXSG) now sits under Benton 1977; the "Two Faces of Power" PDF (HJ9VVIYC) under a new Bachrach & Baratz 1962 APSR record.
- **Item types:** Powers of Theory (F9WYF7N3) web page → book, Alford & Friedland, CUP 1985. Lenin and Philosophy (48N5P9EB) journal article → book, Althusser (author), Brewster (translator), NLB 1971.
- **Wilkinson & Oliver 1988 (XLMZHJKW):** Clegg gives no title; it is the editorial of Industrial Relations Journal 19(1); title "Editorial" and DOI added.
- **Cutler et al. (FGZKSJGW, MXGPAFPE):** not duplicates (Clegg cites vols 1 and 2, 1979a/b). Volume numbers swapped so that FGZKSJGW (with the vol. 1 ISBN) is vol. 1.
- **Dates:** blank dates filled from Clegg (Anderson 1964 and 1977, Baechler 1975, Berger & Luckmann 1966). Thirteen items dated as later reprints keep their edition and got Clegg's year in Zotero's Original Date field (e.g. Reading Capital 2024, original 1970).

- **Identifiers moved into the proper fields (tag `clegg-ids-in-fields`):** 113 DOIs/ISBNs that had been parked in Extra as "Other edition …" lines are now in the DOI/ISBN fields. Some belong to a different edition than the one recorded (e.g. a 2014 reprint DOI on a 1948 record); the old Extra lines, with their edition years, are in `zotero_write/backup_extra_before_move.json`.
- **Two more web pages converted:** Baechler, The Origins of Capitalism (V4USIPDB) → book, Blackwell 1975; Ball, "Models of Power: Past and Present" (FFJSQYPE) → journal article, J. Hist. Behavioral Sciences 11(3).
- **Still in Extra (no free field):** Benton 1977 keeps the 2014 reprint ISBN (its ISBN field has the 1977 one); Jessop 1987 is a manuscript (no ISBN field) and the ISBN is the 1989 book's.

## Checked and left as is (they match Clegg)
- Jessop 1987 (MU9WL97S): Clegg cites an unpublished mimeo, so "manuscript 1987" is right. The DOI in Extra is the 1989 published chapter.
- Meyer 1987 (78YL4UN7): a 1987 conference paper in Clegg; the DOI in Extra is the Theory and Society version.
- Savage 1982 (3JGBN8H6): "The Social Theory of Talcott Parsons" is the title Clegg gives; the actual book is "The Theories of Talcott Parsons" (Macmillan 1981).
- Baratz 1977 review (KXNNLW7L), Hindess 1989 forthcoming (AVL9PMWV), Cantrell as author (NGLSLCVR): as in Clegg.
- Author/editor pairs (Connell, Law, Turner, Clegg, Newton, Knights; Dahl, Callon, Soloway, Simon, Russell): correct, not duplicates.
- Spellings: Zotero is right where Clegg's list has typos (Asad, Elliott, Gutman, McLennan, Oestreich, Lieff).

## Still open for Lauren
- V2IC7W53: a saved link to a Columbia course PDF "american_bachrach.pdf" with no file; it is either Two Faces of Power (1962) or Decisions and Nondecisions (1963). Attach it to the right record or delete it.
- Small year differences against Clegg: Abercrombie et al. 1978 (Clegg 1980), Abrahamsson 1980 (1981), Ball 1975 "Power, Causation and Explanation" (1976), Barnes 1984 "On Authority" (1986), Barnes "T.S. Kuhn" 1982 (1981b).
- 29 references still without a DOI or ISBN (see clegg_identifiers.csv, status not_found).
