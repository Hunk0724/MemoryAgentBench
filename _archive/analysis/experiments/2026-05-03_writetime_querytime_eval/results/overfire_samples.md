# Over-fire Sample Inspection

> 112 of 290 UPDATE events (38.6%) don't match any GT pair.
> Sampling 20 random ones to see if they're (a) spurious or (b) legit supersessions outside our GT.

---

### Over-fire #1

- **old_memory**: `Country Joe McDonald is a citizen of the United States of America`
- **new_memory**: `Country Joe McDonald is a citizen of Romania`
- created_at: 2026-05-02T09:10:42.781407-07:00
- partial entity overlap with GT pairs:
  - GT pair from SH: `Gennady Rozhdestvensky died in the city of Moscow.` → `Gennady Rozhdestvensky died in the city of United States of `
    common words: ['america', 'united', 'states']
  - GT pair from SH: `baseball was created in the country of United States of Amer` → `baseball was created in the country of Japan.`
    common words: ['country', 'america', 'united', 'states']
  - GT pair from SH: `rap rock was created in the country of United States of Amer` → `rap rock was created in the country of Russian Empire.`
    common words: ['country', 'america', 'united', 'states']

### Over-fire #2

- **old_memory**: `Kylie Minogue speaks English`
- **new_memory**: `Kylie Minogue speaks English and German`
- created_at: 2026-05-02T09:07:12.504761-07:00
- partial entity overlap with GT pairs:
  - GT pair from SH: `The official language of United States of America is America` → `The official language of United States of America is German.`
    common words: ['english', 'german']
  - GT pair from SH: `Hermione Granger was performed by Emma Watson.` → `Hermione Granger was performed by Kylie Minogue.`
    common words: ['minogue', 'kylie']
  - GT pair from SH: `Kylie Minogue speaks the language of English.` → `Kylie Minogue speaks the language of German.`
    common words: ['minogue', 'speaks', 'kylie', 'german', 'english']

### Over-fire #3

- **old_memory**: `Friedrich Nietzsche is famous for Thus Spoke Zarathustra and is the author of The Birth of Tragedy`
- **new_memory**: `Friedrich Nietzsche is the author of The Birth of Tragedy`
- created_at: 2026-05-02T09:06:44.120636-07:00
- partial entity overlap with GT pairs:
  - GT pair from MH q91 hop0: `The author of The Birth of Tragedy is Friedrich Nietzsche.` → `The author of The Birth of Tragedy is Stephen Crane.`
    common words: ['author', 'nietzsche', 'tragedy', 'birth', 'friedrich']

### Over-fire #4

- **old_memory**: `Adalbert of Prague is affiliated with the Catholic Church`
- **new_memory**: `Adalbert of Prague is affiliated with the religion of atheism`
- created_at: 2026-05-02T09:10:42.761432-07:00
- partial entity overlap with GT pairs:
  - GT pair from SH: `Kingdom of Ireland is affiliated with the religion of Cathol` → `Kingdom of Ireland is affiliated with the religion of Zoroas`
    common words: ['religion', 'church', 'affiliated', 'catholic']
  - GT pair from SH: `Imelda Marcos is affiliated with the religion of Catholicism` → `Imelda Marcos is affiliated with the religion of atheism.`
    common words: ['religion', 'atheism', 'affiliated']
  - GT pair from SH: `Karen Armstrong is affiliated with the religion of Catholic ` → `Karen Armstrong is affiliated with the religion of Church of`
    common words: ['religion', 'church', 'affiliated', 'catholic']

### Over-fire #5

- **old_memory**: `The chief executive officer of Twitter is Bernard Arnault`
- **new_memory**: `Bernard Arnault is a citizen of France`
- created_at: 2026-05-02T09:06:58.356414-07:00
- partial entity overlap with GT pairs:
  - GT pair from SH: `Cédric Klapisch is a citizen of France.` → `Cédric Klapisch is a citizen of Malaysia.`
    common words: ['citizen', 'france']
  - GT pair from SH: `The chief executive officer of Microsoft is Satya Nadella.` → `The chief executive officer of Microsoft is Steve Jobs.`
    common words: ['chief', 'officer', 'executive']
  - GT pair from SH: `The chief executive officer of Twitter is Jack Dorsey.` → `The chief executive officer of Twitter is Bernard Arnault.`
    common words: ['arnault', 'officer', 'twitter', 'executive', 'bernard', 'chief']

### Over-fire #6

- **old_memory**: `Bill Frisell was educated at Berklee College of Music`
- **new_memory**: `Bill Frisell was educated at The University of the Arts`
- created_at: 2026-05-02T09:07:12.539354-07:00
- partial entity overlap with GT pairs:
  - GT pair from MH q5 hop1: `The univeristy where Wilhelm II was educated is University o` → `The univeristy where Wilhelm II was educated is Baldwin Wall`
    common words: ['university', 'educated']
  - GT pair from MH q30 hop1: `The univeristy where Lou Reed was educated is Syracuse Unive` → `The univeristy where Lou Reed was educated is Fordham Univer`
    common words: ['university', 'educated']
  - GT pair from MH q68 hop1: `The univeristy where Samuel Beckett was educated is Trinity ` → `The univeristy where Samuel Beckett was educated is Universi`
    common words: ['university', 'college', 'educated']

### Over-fire #7

- **old_memory**: `Slovakia national football team plays association football`
- **new_memory**: `Slovakia national football team is associated with the sport of cricket`
- created_at: 2026-05-02T09:06:35.102774-07:00
- partial entity overlap with GT pairs:
  - GT pair from SH: `goaltender is associated with the sport of ice hockey.` → `goaltender is associated with the sport of pesäpallo.`
    common words: ['associated', 'sport']
  - GT pair from SH: `Tunisia national football team is associated with the sport ` → `Tunisia national football team is associated with the sport `
    common words: ['football', 'national', 'associated', 'association', 'sport']
  - GT pair from SH: `quarterback is associated with the sport of American footbal` → `quarterback is associated with the sport of Muay Thai.`
    common words: ['football', 'sport', 'associated']

### Over-fire #8

- **old_memory**: `Born in the U.S.A. was performed by Bruce Springsteen`
- **new_memory**: `Blood on the Tracks was performed by Lou Reed`
- created_at: 2026-05-02T09:06:44.167521-07:00
- partial entity overlap with GT pairs:
  - GT pair from MH q30 hop0: `Blood on the Tracks was performed by Bob Dylan.` → `Blood on the Tracks was performed by Lou Reed.`
    common words: ['tracks', 'blood', 'performed']
  - GT pair from MH q97 hop0: `Born in the U.S.A. was performed by Bruce Springsteen.` → `Born in the U.S.A. was performed by Dana International.`
    common words: ['bruce', 'springsteen', 'u.s.a.', 'performed']

### Over-fire #9

- **old_memory**: `David Bowie performed Aladdin Sane`
- **new_memory**: `David Bowie is married to Iman`
- created_at: 2026-05-02T09:06:35.116033-07:00
- partial entity overlap with GT pairs:
  - GT pair from MH q75 hop0: `Aladdin Sane was performed by David Bowie.` → `Aladdin Sane was performed by Yves Montand.`
    common words: ['aladdin', 'bowie', 'performed', 'david']

### Over-fire #10

- **old_memory**: `Thomas Kyd was born in London`
- **new_memory**: `Thomas Kyd was born in the city of Leeds`
- created_at: 2026-05-02T09:09:50.530413-07:00
- partial entity overlap with GT pairs:
  - GT pair from MH q7 hop0: `Thomas Arne was born in the city of London.` → `Thomas Arne was born in the city of Bengaluru.`
    common words: ['thomas', 'london']
  - GT pair from MH q42 hop1: `Thomas Kyd was born in the city of London.` → `Thomas Kyd was born in the city of Leeds.`
    common words: ['leeds', 'thomas', 'london']

### Over-fire #11

- **old_memory**: `David Bowie performed Aladdin Sane`
- **new_memory**: `David Bowie is married to Iman`
- created_at: 2026-05-02T09:09:50.607006-07:00
- partial entity overlap with GT pairs:
  - GT pair from MH q75 hop0: `Aladdin Sane was performed by David Bowie.` → `Aladdin Sane was performed by Yves Montand.`
    common words: ['aladdin', 'bowie', 'performed', 'david']

### Over-fire #12

- **old_memory**: `Israel was founded by David Ben-Gurion and is located in the continent of Asia`
- **new_memory**: `Israel is located in North America`
- created_at: 2026-05-02T09:06:44.129063-07:00
- partial entity overlap with GT pairs:
  - GT pair from SH: `Germany is located in the continent of Europe.` → `Germany is located in the continent of Africa.`
    common words: ['located', 'continent']
  - GT pair from SH: `Malaysia is located in the continent of Asia.` → `Malaysia is located in the continent of Antarctica.`
    common words: ['located', 'continent']
  - GT pair from SH: `Bengaluru is located in the continent of Asia.` → `Bengaluru is located in the continent of Oceania.`
    common words: ['located', 'continent']

### Over-fire #13

- **old_memory**: `Lisa Leslie is a center`
- **new_memory**: `Lisa Leslie plays the position of goaltender`
- created_at: 2026-05-02T09:09:50.575891-07:00
- partial entity overlap with GT pairs:
  - GT pair from SH: `Robert Parish plays the position of center.` → `Robert Parish plays the position of quarterback.`
    common words: ['position', 'plays', 'center']
  - GT pair from SH: `Hines Ward plays the position of wide receiver.` → `Hines Ward plays the position of cornerback.`
    common words: ['position', 'plays']
  - GT pair from SH: `Rogério Ceni plays the position of goalkeeper.` → `Rogério Ceni plays the position of flanker.`
    common words: ['position', 'plays']

### Over-fire #14

- **old_memory**: `Olga of Kiev died in Kyiv`
- **new_memory**: `Olga of Kiev died in the city of Rodez`
- created_at: 2026-05-02T09:07:12.509985-07:00
- ❌ no GT pair shares any entity word with this event

### Over-fire #15

- **old_memory**: `Andrzej Sapkowski wrote The Witcher`
- **new_memory**: `Andrzej Sapkowski wrote The Witcher and speaks the language of Polish`
- created_at: 2026-05-02T09:06:35.127688-07:00
- partial entity overlap with GT pairs:
  - GT pair from SH: `Kylie Minogue speaks the language of English.` → `Kylie Minogue speaks the language of German.`
    common words: ['speaks', 'language']
  - GT pair from MH q37 hop1: `Kylie Minogue speaks the language of English.` → `Kylie Minogue speaks the language of German.`
    common words: ['speaks', 'language']
  - GT pair from MH q49 hop1: `William Waynflete speaks the language of English.` → `William Waynflete speaks the language of Latin.`
    common words: ['speaks', 'language']

### Over-fire #16

- **old_memory**: `David Beckham is associated with association football`
- **new_memory**: `David Beckham is associated with the sport of cricket`
- created_at: 2026-05-02T09:07:12.528820-07:00
- partial entity overlap with GT pairs:
  - GT pair from SH: `goaltender is associated with the sport of ice hockey.` → `goaltender is associated with the sport of pesäpallo.`
    common words: ['associated', 'sport']
  - GT pair from SH: `Tunisia national football team is associated with the sport ` → `Tunisia national football team is associated with the sport `
    common words: ['football', 'sport', 'association', 'associated']
  - GT pair from SH: `quarterback is associated with the sport of American footbal` → `quarterback is associated with the sport of Muay Thai.`
    common words: ['football', 'sport', 'associated']

### Over-fire #17

- **old_memory**: `Pius XII died in Castel Gandolfo`
- **new_memory**: `Pius XII died in the city of Wolverhampton`
- created_at: 2026-05-02T09:07:12.490784-07:00
- partial entity overlap with GT pairs:
  - GT pair from MH q74 hop1: `Pius XII died in the city of Castel Gandolfo.` → `Pius XII died in the city of Wolverhampton.`
    common words: ['wolverhampton', 'gandolfo', 'castel']

### Over-fire #18

- **old_memory**: `Laura Bush is married to George W. Bush`
- **new_memory**: `Laura Bush is married to George W. Bush`
- created_at: 2026-05-02T09:10:13.736869-07:00
- partial entity overlap with GT pairs:
  - GT pair from MH q13 hop0: `Laura Bush is married to George W. Bush.` → `Laura Bush is married to Princess Alice, Duchess of Gloucest`
    common words: ['laura', 'george', 'married']

### Over-fire #19

- **old_memory**: `Tim Cook is the CEO of Apple Inc.`
- **new_memory**: `Tim Cook is the CEO of Apple Inc.`
- created_at: 2026-05-02T09:09:50.573229-07:00
- ❌ no GT pair shares any entity word with this event

### Over-fire #20

- **old_memory**: `Chang'an is the capital of the Tang Empire`
- **new_memory**: `Capital of Tang Empire is Beaumont`
- created_at: 2026-05-02T09:09:50.595362-07:00
- partial entity overlap with GT pairs:
  - GT pair from SH: `The capital of Tang Empire is Chang'an.` → `The capital of Tang Empire is Beaumont.`
    common words: ['beaumont', 'capital', 'empire', "chang'an"]
  - GT pair from MH q54 hop3: `The capital of Tang Empire is Chang'an.` → `The capital of Tang Empire is Beaumont.`
    common words: ['beaumont', 'capital', 'empire', "chang'an"]

---

## How to interpret

- **No GT overlap** + plausible facts: 大概是「FC 6k context 中有但不在 100 題覆蓋的真實 supersession」 → 不算 spurious
- **No GT overlap** + nonsense pairing: 真 spurious — Mem0 LLM Update Memory 步驟錯把無關的 fact 當衝突
- **Has overlap + reverse direction confusion**: 同一 entity 兩 GT pair（e.g., MH chain 中 hop0+hop1）被 Mem0 串到一起當 supersession，FC chain 結構觸發的特殊 case