# `b` (mem0+P1) has_pair wrong-qid write-event attribution

- Method: `(b) mem0+P1` = MABench mem0 with our L2/unified extractor prompt (P1).
- Backbone: gpt-4o-mini @ temp 0, chunk 512.
- For each has_pair query we located the LATEST ingest-time event(s) whose
  extracted-memory text matches this fact's shared stem AND at least one of the
  new/old object tokens, then classified by event type + presence.

## Summary — bucket counts across lengths (wrong-qid only)

| Bucket | 6k wrong | 32k wrong | 64k wrong |
| :--- | ---: | ---: | ---: |
| A. UPDATE_kept_new | 7 | 9 | 10 |
| B. ADD_both_coexist | 10 | 8 | 8 |
| B'. ADD_new_only | 4 | 2 | 3 |
| C1. DELETE_dropped_new | 6 | 8 | 7 |
| C2. DELETE_lost_new | 4 | 2 | 0 |
| D. NONE_silent_drop | 8 | 6 | 5 |
| E. Ambiguous (old_UPDATE, no new) | 1 | 1 | 6 |

| **Total wrong** | **40** | **36** | **39** |

## Summary — bucket counts (correct-qid, control)

| Bucket | 6k correct | 32k correct | 64k correct |
| :--- | ---: | ---: | ---: |
| A. UPDATE_kept_new | 8 | 9 | 8 |
| B. ADD_both_coexist | 8 | 10 | 6 |
| B'. ADD_new_only | 4 | 2 | 4 |
| C1. DELETE_dropped_new | 2 | 5 | 5 |
| C2. DELETE_lost_new | 3 | 2 | 1 |
| D. NONE_silent_drop | 9 | 0 | 3 |
| E. Ambiguous (old_UPDATE, no new) | 0 | 1 | 0 |
| **Total correct** | **34** | **29** | **27** |

## 6k — has_pair n=74, wrong=40, correct=34, ingest_events=352

### Sample wrong-qid cases (up to 3 per bucket)

- **A. UPDATE_kept_new** qid=19
  - GT_new: `The chief executive officer of Microsoft is Steve Jobs.`
  - GT_old: `The chief executive officer of Microsoft is Satya Nadella.`
  - chunk=4 event=ADD [N] memory=`The chief executive officer of Microsoft is Steve Jobs.`
  - chunk=9 event=UPDATE [N] memory=`The chief executive officer of Microsoft is Steve Jobs.`

- **A. UPDATE_kept_new** qid=23
  - GT_new: `The director of American Broadcasting Company is Ernst Heinkel.`
  - GT_old: `The director of American Broadcasting Company is Bob Iger.`
  - chunk=1 event=ADD [NO] memory=`The director of American Broadcasting Company is Bob Iger`
  - chunk=10 event=UPDATE [NO] memory=`The director of American Broadcasting Company is Ernst Heinkel.`

- **A. UPDATE_kept_new** qid=56
  - GT_new: `Charlie Hebdo was created in the country of Italy.`
  - GT_old: `Charlie Hebdo was created in the country of France.`
  - chunk=9 event=DELETE [NO] memory=`Charlie Hebdo was created in the country of France.`
  - chunk=9 event=ADD [NO] memory=`Charlie Hebdo was created in the country of Italy.`
  - chunk=10 event=UPDATE [NO] memory=`Charlie Hebdo was created in the country of Italy.`

- **B. ADD_both_coexist** qid=12
  - GT_new: `Robert Parish plays the position of quarterback.`
  - GT_old: `Robert Parish plays the position of center.`
  - chunk=8 event=ADD [NO] memory=`Robert Parish plays the position of center.`
  - chunk=8 event=ADD [NO] memory=`Robert Parish plays the position of quarterback.`

- **B. ADD_both_coexist** qid=15
  - GT_new: `Germany is located in the continent of Africa.`
  - GT_old: `Germany is located in the continent of Europe.`
  - chunk=11 event=ADD [O] memory=`France is located in the continent of Europe.`
  - chunk=11 event=ADD [NO] memory=`Germany is located in the continent of Africa.`
  - chunk=11 event=ADD [N] memory=`Canada is located in the continent of Asia.`

- **B. ADD_both_coexist** qid=28
  - GT_new: `The type of music that Michael Mantler plays is post-punk.`
  - GT_old: `The type of music that Michael Mantler plays is jazz.`
  - chunk=7 event=ADD [NO] memory=`The type of music that Michael Mantler plays is jazz.`
  - chunk=7 event=ADD [NO] memory=`The type of music that Michael Mantler plays is post-punk.`

- **B'. ADD_new_only** qid=39
  - GT_new: `SteamOS was developed by ABB Group.`
  - GT_old: `SteamOS was developed by Valve Corporation.`
  - chunk=7 event=ADD [N] memory=`SteamOS was developed by ABB Group.`

- **B'. ADD_new_only** qid=70
  - GT_new: `The company that produced AP1000 is Canadair.`
  - GT_old: `The company that produced AP1000 is Westinghouse Electric.`
  - chunk=9 event=ADD [N] memory=`The company that produced AP1000 is Canadair.`

- **B'. ADD_new_only** qid=73
  - GT_new: `Tony Blair is married to Alan Jay Lerner.`
  - GT_old: `Tony Blair is married to Cherie Blair.`
  - chunk=3 event=ADD [O] memory=`Tony Blair is married to Cherie Blair.`
  - chunk=11 event=DELETE [O] memory=`Tony Blair is married to Cherie Blair.`
  - chunk=11 event=ADD [N] memory=`Tony Blair is married to Alan Jay Lerner.`

- **C1. DELETE_dropped_new** qid=38
  - GT_new: `The capital of France is Harare.`
  - GT_old: `The capital of France is Paris.`
  - chunk=4 event=DELETE [NO] memory=`The capital of France is Harare.`

- **C1. DELETE_dropped_new** qid=43
  - GT_new: `The capital of Australia is Oderzo.`
  - GT_old: `The capital of Australia is Canberra.`
  - chunk=7 event=ADD [NO] memory=`The capital of Australia is Canberra.`
  - chunk=10 event=DELETE [NO] memory=`The capital of Australia is Canberra.`

- **C1. DELETE_dropped_new** qid=50
  - GT_new: `Bengaluru is located in the continent of Oceania.`
  - GT_old: `Bengaluru is located in the continent of Asia.`
  - chunk=9 event=ADD [O] memory=`Malaysia is located in the continent of Asia.`
  - chunk=11 event=DELETE [O] memory=`Malaysia is located in the continent of Asia.`
  - chunk=11 event=ADD [O] memory=`Canada is located in the continent of Asia.`

- **C2. DELETE_lost_new** qid=5
  - GT_new: `The author of The Marriage of Figaro is Thomas Kyd.`
  - GT_old: `The author of The Marriage of Figaro is Pierre Beaumarchais.`
  - chunk=7 event=ADD [O] memory=`The author of The Marriage of Figaro is Pierre Beaumarchais.`
  - chunk=10 event=DELETE [O] memory=`The author of The Marriage of Figaro is Pierre Beaumarchais.`

- **C2. DELETE_lost_new** qid=7
  - GT_new: `quarterback is associated with the sport of Muay Thai.`
  - GT_old: `quarterback is associated with the sport of American football.`
  - chunk=2 event=UPDATE [O] memory=`Placekicker is associated with the sport of American football.`
  - chunk=8 event=ADD [O] memory=`Cornerback is associated with the sport of American football.`
  - chunk=9 event=DELETE [O] memory=`Cornerback is associated with the sport of American football.`

- **C2. DELETE_lost_new** qid=26
  - GT_new: `The director of British Broadcasting Corporation is Narendra Modi.`
  - GT_old: `The director of British Broadcasting Corporation is Tony Hall, Baron Hall of Birkenhead.`
  - chunk=0 event=ADD [O] memory=`The director of British Broadcasting Corporation is Tony Hall, Baron Hall of Birkenhead`
  - chunk=11 event=DELETE [O] memory=`The director of British Broadcasting Corporation is Tony Hall, Baron Hall of Birkenhead`

- **D. NONE_silent_drop** qid=14
  - GT_new: `The author of Sidereus Nuncius is Samuel Beckett.`
  - GT_old: `The author of Sidereus Nuncius is Galileo Galilei.`
  - chunk=3 event=ADD [O] memory=`The author of Sidereus Nuncius is Galileo Galilei.`

- **D. NONE_silent_drop** qid=17
  - GT_new: `association football was created in the country of Italy.`
  - GT_old: `association football was created in the country of England.`
  - No relevant events matched this fact.

- **D. NONE_silent_drop** qid=33
  - GT_new: `rap rock was created in the country of Russian Empire.`
  - GT_old: `rap rock was created in the country of United States of America.`
  - chunk=2 event=ADD [O] memory=`Club Nouveau was created in the country of United States of America.`
  - chunk=9 event=DELETE [O] memory=`Club Nouveau was created in the country of United States of America.`
  - chunk=9 event=ADD [O] memory=`Rap rock was created in the country of United States of America.`

- **E. Ambiguous (old_UPDATE, no new)** qid=83
  - GT_new: `Karen Armstrong is affiliated with the religion of Church of Scotland.`
  - GT_old: `Karen Armstrong is affiliated with the religion of Catholic Church.`
  - chunk=7 event=ADD [O] memory=`John Walsh is affiliated with the religion of Catholic Church.`
  - chunk=9 event=UPDATE [O] memory=`John Walsh is affiliated with the religion of Catholic Church.`


## 32k — has_pair n=65, wrong=36, correct=29, ingest_events=2031

### Sample wrong-qid cases (up to 3 per bucket)

- **A. UPDATE_kept_new** qid=20
  - GT_new: `Tony Parker plays the position of shooting guard.`
  - GT_old: `Tony Parker plays the position of point guard.`
  - chunk=44 event=ADD [NO] memory=`Tony Parker plays the position of point guard.`
  - chunk=49 event=UPDATE [NO] memory=`Tony Parker plays the position of point guard.`
  - chunk=51 event=ADD [O] memory=`Ty Lawson plays the position of point guard.`

- **A. UPDATE_kept_new** qid=41
  - GT_new: `The chief executive officer of Apple Inc. is Vijay Mallya.`
  - GT_old: `The chief executive officer of Apple Inc. is Tim Cook.`
  - chunk=15 event=ADD [NO] memory=`The chief executive officer of Apple Inc. is Tim Cook.`
  - chunk=28 event=UPDATE [NO] memory=`The chief executive officer of Apple Inc. is Tim Cook.`

- **A. UPDATE_kept_new** qid=42
  - GT_new: `Sabbatai Zevi works in the field of superhero.`
  - GT_old: `Sabbatai Zevi works in the field of rabbi.`
  - chunk=25 event=ADD [NO] memory=`Sabbatai Zevi works in the field of rabbi.`
  - chunk=42 event=UPDATE [NO] memory=`Sabbatai Zevi works in the field of superhero.`

- **B. ADD_both_coexist** qid=2
  - GT_new: `power forward is associated with the sport of rugby.`
  - GT_old: `power forward is associated with the sport of basketball.`
  - chunk=42 event=ADD [O] memory=`Jeff Hornacek is associated with the sport of basketball.`
  - chunk=45 event=ADD [N] memory=`Small forward is associated with the sport of rugby.`
  - chunk=63 event=UPDATE [O] memory=`New Firm is associated with the sport of baseball.`

- **B. ADD_both_coexist** qid=3
  - GT_new: `Morris Iemma is affiliated with the religion of Methodism.`
  - GT_old: `Morris Iemma is affiliated with the religion of Catholic Church.`
  - chunk=49 event=UPDATE [O] memory=`Lady Gaga is affiliated with the religion of Catholic Church.`
  - chunk=50 event=ADD [N] memory=`Henri Breuil is affiliated with the religion of Methodism.`
  - chunk=55 event=ADD [O] memory=`Andrzej Duda is affiliated with the religion of Catholic Church.`

- **B. ADD_both_coexist** qid=15
  - GT_new: `Rick Remender is a citizen of Italy.`
  - GT_old: `Rick Remender is a citizen of United States of America.`
  - chunk=41 event=ADD [O] memory=`Bob Iger is a citizen of United States of America.`
  - chunk=43 event=ADD [O] memory=`Dina Merrill is a citizen of United States of America.`
  - chunk=44 event=ADD [O] memory=`Hal Erickson is a citizen of United States of America.`

- **B'. ADD_new_only** qid=52
  - GT_new: `Past Masters was performed by Madonna.`
  - GT_old: `Past Masters was performed by The Beatles.`
  - chunk=42 event=ADD [N] memory=`Past Masters was performed by Madonna.`

- **B'. ADD_new_only** qid=83
  - GT_new: `Madame du Barry is a citizen of Great Britain.`
  - GT_old: `Madame du Barry is a citizen of France.`
  - chunk=55 event=ADD [N] memory=`Madame du Barry is a citizen of Great Britain.`

- **C1. DELETE_dropped_new** qid=5
  - GT_new: `The capital of United Kingdom is Rupnagar.`
  - GT_old: `The capital of United Kingdom is London.`
  - chunk=21 event=ADD [NO] memory=`The capital of United Kingdom is Rupnagar.`
  - chunk=33 event=DELETE [NO] memory=`The capital of United Kingdom is Rupnagar.`

- **C1. DELETE_dropped_new** qid=47
  - GT_new: `San Francisco is located in the continent of Africa.`
  - GT_old: `San Francisco is located in the continent of North America.`
  - chunk=45 event=DELETE [NO] memory=`San Francisco is located in the continent of Africa.`
  - chunk=45 event=ADD [O] memory=`France is located in the continent of North America.`
  - chunk=58 event=UPDATE [O] memory=`Ireland is located in the continent of North America.`

- **C1. DELETE_dropped_new** qid=53
  - GT_new: `Imran Khan is associated with the sport of association football.`
  - GT_old: `Imran Khan is associated with the sport of cricket.`
  - chunk=57 event=ADD [N] memory=`Maccabi Yavne F.C. is associated with the sport of association football.`
  - chunk=59 event=UPDATE [N] memory=`Bob Bradley is associated with the sport of association football.`
  - chunk=61 event=DELETE [N] memory=`Bo Ryan is associated with the sport of association football.`

- **C2. DELETE_lost_new** qid=27
  - GT_new: `midfielder is associated with the sport of sumo.`
  - GT_old: `midfielder is associated with the sport of association football.`
  - chunk=57 event=UPDATE [O] memory=`Diego Simeone is associated with the sport of association football.`
  - chunk=59 event=UPDATE [O] memory=`Bob Bradley is associated with the sport of association football.`
  - chunk=61 event=DELETE [O] memory=`Bo Ryan is associated with the sport of association football.`

- **C2. DELETE_lost_new** qid=77
  - GT_new: `Cédric Klapisch is a citizen of Malaysia.`
  - GT_old: `Cédric Klapisch is a citizen of France.`
  - chunk=14 event=ADD [O] memory=`Cédric Klapisch is a citizen of France`
  - chunk=19 event=DELETE [O] memory=`Cédric Klapisch is a citizen of France`

- **D. NONE_silent_drop** qid=17
  - GT_new: `Charles Darwin is married to Amala Paul.`
  - GT_old: `Charles Darwin is married to Emma Darwin.`
  - chunk=15 event=ADD [O] memory=`Charles Darwin is married to Emma Darwin.`

- **D. NONE_silent_drop** qid=46
  - GT_new: `The author of Inuyasha is Terrance Dicks.`
  - GT_old: `The author of Inuyasha is Rumiko Takahashi.`
  - chunk=43 event=ADD [O] memory=`The author of Inuyasha is Rumiko Takahashi.`

- **D. NONE_silent_drop** qid=49
  - GT_new: `2009 Six Nations Championship is associated with the sport of association football.`
  - GT_old: `2009 Six Nations Championship is associated with the sport of rugby union.`
  - No relevant events matched this fact.

- **E. Ambiguous (old_UPDATE, no new)** qid=67
  - GT_new: `Sue Grafton is a citizen of Ukraine.`
  - GT_old: `Sue Grafton is a citizen of United States of America.`
  - chunk=47 event=ADD [O] memory=`Pat Nixon is a citizen of United States of America.`
  - chunk=60 event=ADD [O] memory=`Leo Gordon is a citizen of United States of America.`
  - chunk=63 event=UPDATE [O] memory=`David Crane is a citizen of United States of America.`


## 64k — has_pair n=66, wrong=39, correct=27, ingest_events=3713

### Sample wrong-qid cases (up to 3 per bucket)

- **A. UPDATE_kept_new** qid=0
  - GT_new: `The New York Times was written in the language of Ancient Greek.`
  - GT_old: `The New York Times was written in the language of English.`
  - chunk=105 event=ADD [O] memory=`The Thorn Birds was written in the language of English.`
  - chunk=110 event=ADD [O] memory=`The Wheel of Time was written in the language of English.`
  - chunk=115 event=UPDATE [NO] memory=`The New York Times was written in the language of Ancient Greek.`

- **A. UPDATE_kept_new** qid=16
  - GT_new: `The head coach of Burnley F.C. is Jeff Hornacek.`
  - GT_old: `The head coach of Burnley F.C. is Sean Dyche.`
  - chunk=63 event=UPDATE [N] memory=`The head coach of Burnley F.C. is Jeff Hornacek.`
  - chunk=64 event=DELETE [O] memory=`The head coach of Burnley F.C. is Sean Dyche.`
  - chunk=72 event=UPDATE [N] memory=`The head coach of Burnley F.C. is Jeff Hornacek.`

- **A. UPDATE_kept_new** qid=24
  - GT_new: `Philip II of Spain is a citizen of United Kingdom.`
  - GT_old: `Philip II of Spain is a citizen of Spain.`
  - chunk=58 event=ADD [O] memory=`Philip II of Spain is a citizen of Spain.`
  - chunk=61 event=UPDATE [N] memory=`Paul I of Russia is a citizen of United Kingdom.`
  - chunk=68 event=UPDATE [N] memory=`Philip II of Spain is a citizen of United Kingdom.`

- **B. ADD_both_coexist** qid=5
  - GT_new: `The type of music that Aki Takase plays is Carnatic music.`
  - GT_old: `The type of music that Aki Takase plays is jazz.`
  - chunk=104 event=UPDATE [O] memory=`The type of music that Nat King Cole plays is jazz.`
  - chunk=114 event=ADD [N] memory=`The type of music that Purandara Dasa plays is Carnatic music.`
  - chunk=122 event=ADD [O] memory=`The type of music that Billy Taylor plays is jazz.`

- **B. ADD_both_coexist** qid=22
  - GT_new: `The Orange County Register was created in the country of United Kingdom.`
  - GT_old: `The Orange County Register was created in the country of United States of America.`
  - chunk=49 event=ADD [O] memory=`The Forester Sisters was created in the country of United States of America.`
  - chunk=94 event=ADD [O] memory=`Peanuts was created in the country of United States of America.`
  - chunk=120 event=ADD [NO] memory=`The Orange County Register was created in the country of United Kingdom.`

- **B. ADD_both_coexist** qid=48
  - GT_new: `The official language of Kingdom of the Netherlands is Old Turkic.`
  - GT_old: `The official language of Kingdom of the Netherlands is Dutch.`
  - chunk=88 event=ADD [NO] memory=`The official language of Kingdom of the Netherlands is Old Turkic.`

- **B'. ADD_new_only** qid=40
  - GT_new: `The author of The Andromeda Strain is Multatuli.`
  - GT_old: `The author of The Andromeda Strain is Michael Crichton.`
  - chunk=81 event=ADD [N] memory=`The author of The Andromeda Strain is Multatuli.`

- **B'. ADD_new_only** qid=45
  - GT_new: `Mortal Kombat X was developed by Blizzard Entertainment.`
  - GT_old: `Mortal Kombat X was developed by NetherRealm Studios.`
  - chunk=91 event=ADD [N] memory=`Mortal Kombat X was developed by Blizzard Entertainment.`

- **B'. ADD_new_only** qid=78
  - GT_new: `Dear Prudence was performed by Madonna.`
  - GT_old: `Dear Prudence was performed by The Beatles.`
  - chunk=22 event=ADD [O] memory=`Hey Jude was performed by The Beatles.`
  - chunk=23 event=DELETE [O] memory=`Hey Jude was performed by The Beatles.`
  - chunk=88 event=ADD [N] memory=`Dear Prudence was performed by Madonna.`

- **C1. DELETE_dropped_new** qid=11
  - GT_new: `Prince Andrew, Duke of York is married to Mahidol Adulyadej.`
  - GT_old: `Prince Andrew, Duke of York is married to Sarah, Duchess of York.`
  - chunk=99 event=ADD [N] memory=`Prince Andrew, Duke of York is married to Mahidol Adulyadej.`
  - chunk=106 event=DELETE [N] memory=`Prince Andrew, Duke of York is married to Mahidol Adulyadej.`

- **C1. DELETE_dropped_new** qid=19
  - GT_new: `The official language of Soviet Union is French.`
  - GT_old: `The official language of Soviet Union is Russian.`
  - chunk=106 event=DELETE [NO] memory=`The official language of Soviet Union is Russian.`
  - chunk=106 event=ADD [NO] memory=`The official language of Soviet Union is French.`
  - chunk=116 event=DELETE [N] memory=`The official language of Indonesia is French.`

- **C1. DELETE_dropped_new** qid=20
  - GT_new: `Great Britain is located in the continent of Europe.`
  - GT_old: `Great Britain is located in the continent of Asia.`
  - chunk=107 event=ADD [O] memory=`Serbia is located in the continent of Asia.`
  - chunk=112 event=DELETE [O] memory=`Argentina is located in the continent of Asia.`
  - chunk=121 event=ADD [O] memory=`Germany is located in the continent of Africa.`

- **D. NONE_silent_drop** qid=29
  - GT_new: `PowerBook G4 was developed by Microsoft.`
  - GT_old: `PowerBook G4 was developed by Apple Inc..`
  - chunk=58 event=ADD [O] memory=`PowerBook G4 was developed by Apple Inc.`

- **D. NONE_silent_drop** qid=35
  - GT_new: `The univeristy where Ilir Meta was educated is Montana State University - Bozeman.`
  - GT_old: `The univeristy where Ilir Meta was educated is University of Tirana.`
  - chunk=43 event=ADD [O] memory=`The university where Ilir Meta was educated is University of Tirana.`

- **D. NONE_silent_drop** qid=59
  - GT_new: `bluegrass music was created in the country of Indonesia.`
  - GT_old: `bluegrass music was created in the country of United States of America.`
  - chunk=110 event=ADD [O] memory=`ESPN was created in the country of United States of America.`
  - chunk=113 event=ADD [O] memory=`country music was created in the country of United States of America.`
  - chunk=117 event=ADD [O] memory=`Basketball was created in the country of United States of America.`

- **E. Ambiguous (old_UPDATE, no new)** qid=1
  - GT_new: `The author of Hard Times is Martin Luther King Jr..`
  - GT_old: `The author of Hard Times is Charles Dickens.`
  - chunk=18 event=ADD [O] memory=`The author of Hard Times is Charles Dickens.`
  - chunk=43 event=UPDATE [O] memory=`The author of Hard Times is Charles Dickens.`
  - chunk=64 event=UPDATE [O] memory=`The author of Hard Times is Charles Dickens.`

- **E. Ambiguous (old_UPDATE, no new)** qid=9
  - GT_new: `Kermit the Frog was created by Hiroshige.`
  - GT_old: `Kermit the Frog was created by Jim Henson.`
  - chunk=45 event=ADD [O] memory=`Kermit the Frog was created by Jim Henson.`
  - chunk=77 event=UPDATE [O] memory=`Kermit the Frog was created by Jim Henson.`

- **E. Ambiguous (old_UPDATE, no new)** qid=60
  - GT_new: `North East Stars is associated with the sport of cricket.`
  - GT_old: `North East Stars is associated with the sport of association football.`
  - chunk=122 event=DELETE [O] memory=`Rio Ave F.C. is associated with the sport of association football.`
  - chunk=124 event=ADD [O] memory=`Lorik Cana is associated with the sport of association football.`
  - chunk=128 event=UPDATE [O] memory=`S.C. Salgueiros is associated with the sport of association football.`

