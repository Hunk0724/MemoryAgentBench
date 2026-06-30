# Case Studies — Mem0 vs Zep on FC conflict handling

> Concrete examples of how Mem0 / Zep handle 12 representative FC questions.
> Mem0 events from `~/.mem0/history.db` filtered to this run (`created_at >= 2026-05-02T07:00:00`).
> Mem0 retrieved memories: only top-5 saved per qid in run JSON (full top-100 was sent to LLM).
> Zep retrieved context: only first 500 chars saved per qid in run JSON.

---

## Quick patterns observed

| Pattern | Cases | Implication |
|---|---|---|
| Mem0 detected → Mem0 retrieved CURRENT only → Mem0 answered correctly | SH qid=0, MH qid=0 | Mem0 paradigm = filter at write; LLM sees clean current state |
| Mem0 missed UPDATE → both old+new stored OR only old stored → Mem0 answered with old | MH qid=1 (Olga Kiev→Rodez missed) | Mem0 silent failure mode: no UPDATE event, retrieval returns world-knowledge-aligned old fact |
| Zep edge has `valid_at - present` for OLD fact (no invalid_at set) → LLM sees both with no clear signal → answered with old | SH qid=0, MH qid=0 | Zep detection silent miss; LLM defaults to world knowledge |
| Zep edge has narrow `valid_at - invalid_at` window for NEW fact (wrong direction) | SH qid=22 | counterfactual bias: Zep invalidated the CORRECT fact |
| No has_pair conflict + correct retrieve → both succeed | SH qid=4, qid=11 | baseline competence |

---

### SH qid=0

**Question**: Which sport is goaltender associated with?

**Ground truth answer**: `pesäpallo`

#### Ground-truth has_pair chain (1 pairs):

- old (seq 223): `goaltender is associated with the sport of ice hockey.`
  → new (seq 310): `goaltender is associated with the sport of pesäpallo.`

#### Mem0 history.db events touching these pairs:

- `ADD`: 
  - new_memory: `goaltender is associated with the sport of ice hockey`
- `UPDATE`: 
  - old_memory: `goaltender is associated with the sport of ice hockey`
  - new_memory: `Goaltender is associated with the sport of pesäpallo`
- `ADD`: 
  - new_memory: `goaltender is associated with the sport of ice hockey`
- `UPDATE`: 
  - old_memory: `goaltender is associated with the sport of ice hockey`
  - new_memory: `Goaltender is associated with the sport of pesäpallo`

#### Mem0 retrieved (top of 100, only top-5 saved per qid) + answer:

- Goaltender is associated with the sport of pesäpallo
- Cornerback is associated with field hockey
- Joe Hockey is a citizen of Australia
- Lisa Leslie plays the position of goaltender
- Placekicker is associated with the sport of rugby

**Mem0 pred answer**: `Goaltender is associated with the sport of pesäpallo.`
**Mem0 EM**: ✅

#### Zep retrieved context preview + answer:

- edges=10, nodes=10, episodes=10
- preview (first 500 chars):

  ```
  
  FACTS and ENTITIES represent relevant context to the current conversation.
  
  # These are the most relevant facts and their valid date ranges. If the fact is about an event, the event takes place during this time.
  # format: FACT (Date range: from - to)
  
    - goaltender is associated with the sport of ice hockey. (2026-05-02T14:39:59.762Z - present)
    - point guard is associated with the sport of cricket. (2026-05-02T14:39:59.762Z - present)
    - quarterback is associated with the sport of American 
  ```

**Zep pred answer**: `Goaltender is associated with the sport of ice hockey.`
**Zep EM**: ❌

---

### SH qid=4

**Question**: Which university was Joan Didion educated at?

**Ground truth answer**: `University of California, Berkeley`

#### Ground-truth has_pair chain (0 pairs):

(no has_pair conflict in this question)

#### Mem0 history.db events touching these pairs:

**(none — Mem0 did NOT fire any UPDATE event for this pair)**

#### Mem0 retrieved (top of 100, only top-5 saved per qid) + answer:

- The univeristy where Joan Didion was educated is University of California, Berkeley
- The university where Lou Reed was educated is Fordham University
- Elena Ceaușescu was educated at University of Bucharest
- Wilhelm II was educated at the University of Bonn
- Bill Frisell was educated at The University of the Arts

**Mem0 pred answer**: `Joan Didion was educated at the University of California, Berkeley.`
**Mem0 EM**: ✅

#### Zep retrieved context preview + answer:

- edges=10, nodes=10, episodes=10
- preview (first 500 chars):

  ```
  
  FACTS and ENTITIES represent relevant context to the current conversation.
  
  # These are the most relevant facts and their valid date ranges. If the fact is about an event, the event takes place during this time.
  # format: FACT (Date range: from - to)
  
    - The univeristy where Joan Didion was educated is University of California, Berkeley. (2026-05-02T00:00:00Z - present)
    - Bill Frisell was educated at The University of the Arts. (date unknown - present)
    - The univeristy where Lou Reed was e
  ```

**Zep pred answer**: `Joan Didion was educated at the University of California, Berkeley.`
**Zep EM**: ✅

---

### SH qid=11

**Question**: Who performed Meredith Grey?

**Ground truth answer**: `Ellen Pompeo`

#### Ground-truth has_pair chain (0 pairs):

(no has_pair conflict in this question)

#### Mem0 history.db events touching these pairs:

**(none — Mem0 did NOT fire any UPDATE event for this pair)**

#### Mem0 retrieved (top of 100, only top-5 saved per qid) + answer:

- Meredith Grey was performed by Ellen Pompeo
- Derek Shepherd is married to Meredith Grey
- Hermione Granger was performed by Emma Watson
- Blood on the Tracks was performed by Lou Reed
- Amy Winehouse died in Camden Town

**Mem0 pred answer**: `Meredith Grey was performed by Ellen Pompeo.`
**Mem0 EM**: ✅

#### Zep retrieved context preview + answer:

- edges=10, nodes=10, episodes=10
- preview (first 500 chars):

  ```
  
  FACTS and ENTITIES represent relevant context to the current conversation.
  
  # These are the most relevant facts and their valid date ranges. If the fact is about an event, the event takes place during this time.
  # format: FACT (Date range: from - to)
  
    - Meredith Grey was performed by Ellen Pompeo. (2026-05-02T14:39:58.55Z - present)
    - Derek Shepherd is married to Meredith Grey. (2026-05-02T14:40:01.671Z - present)
    - Past Masters was performed by Madonna. (date unknown - present)
    - Hermi
  ```

**Zep pred answer**: `Meredith Grey was performed by Ellen Pompeo.`
**Zep EM**: ✅

---

### SH qid=22

**Question**: Which sport is Galwegians RFC associated with?

**Ground truth answer**: `rugby union`

#### Ground-truth has_pair chain (0 pairs):

(no has_pair conflict in this question)

#### Mem0 history.db events touching these pairs:

**(none — Mem0 did NOT fire any UPDATE event for this pair)**

#### Mem0 retrieved (top of 100, only top-5 saved per qid) + answer:

- Galwegians RFC plays rugby union
- Gala RFC is associated with the sport of rugby union
- point guard is associated with the sport of cricket
- Slovakia national football team is associated with the sport of cricket
- Sandy Alderson is associated with the sport of association football

**Mem0 pred answer**: `Galwegians RFC is associated with the sport of rugby union.`
**Mem0 EM**: ✅

#### Zep retrieved context preview + answer:

- edges=10, nodes=10, episodes=10
- preview (first 500 chars):

  ```
  
  FACTS and ENTITIES represent relevant context to the current conversation.
  
  # These are the most relevant facts and their valid date ranges. If the fact is about an event, the event takes place during this time.
  # format: FACT (Date range: from - to)
  
    - Galwegians RFC is associated with the sport of rugby union. (2026-05-02T14:39:57.792Z - 2026-05-02T14:39:58.55Z)
    - wide receiver is associated with the sport of rugby. (2026-05-02T14:40:00.137Z - present)
    - flanker is associated with the s
  ```

**Zep pred answer**: `Galwegians RFC is associated with the sport of rugby union.`
**Zep EM**: ✅

---

### MH qid=0

**Question**: What is the country of citizenship of the spouse of the author of Our Mutual Friend?

**Ground truth answer**: `Belgium`
**num_hops**: 3

#### Ground-truth has_pair chain (3 pairs):

- hop 0: old (seq 107): `The author of Our Mutual Friend is Charles Dickens.`
  → new (seq 146): `The author of Our Mutual Friend is Charles Darwin.`
- hop 1: old (seq 164): `Charles Darwin is married to Emma Darwin.`
  → new (seq 335): `Charles Darwin is married to Amala Paul.`
- hop 2: old (seq 294): `Amala Paul is a citizen of India.`
  → new (seq 322): `Amala Paul is a citizen of Belgium.`

#### Mem0 history.db events touching these pairs:

- `ADD` [hop 0]: 
  - new_memory: `The author of Our Mutual Friend is Charles Dickens`
- `UPDATE` [hop 0]: 
  - old_memory: `The author of Our Mutual Friend is Charles Dickens`
  - new_memory: `Author of Our Mutual Friend is Charles Darwin`
- `ADD` [hop 0]: 
  - new_memory: `The author of Our Mutual Friend is Charles Dickens`
- `UPDATE` [hop 0]: 
  - old_memory: `The author of Our Mutual Friend is Charles Dickens`
  - new_memory: `Author of Our Mutual Friend is Charles Darwin`
- `UPDATE` [hop 1]: 
  - old_memory: `Charles Dickens is married to Catherine Dickens`
  - new_memory: `Charles Darwin is married to Emma Darwin`

#### Mem0 retrieved (top of 100, only top-5 saved per qid) + answer:

- Author of Our Mutual Friend is Charles Darwin
- Henri Grégoire is a citizen of India
- Country Joe McDonald is a citizen of Romania
- Leo Stein is a citizen of United States of America
- Amala Paul is a citizen of Belgium

**Mem0 pred answer**: `Based on the provided information:

1.  The author of *Our Mutual Friend* is Charles Darwin.
2.  Charles Darwin is married to Amala Paul.
3.  Amala Paul is a citizen of Belgium.

Therefore, the country of citizenship of the spouse of the author of *Our Mutual Friend* is Belgium.`
**Mem0 EM**: ✅

#### Zep retrieved context preview + answer:

- edges=10, nodes=10, episodes=6
- preview (first 500 chars):

  ```
  
  FACTS and ENTITIES represent relevant context to the current conversation.
  
  # These are the most relevant facts and their valid date ranges. If the fact is about an event, the event takes place during this time.
  # format: FACT (Date range: from - to)
  
    - The author of Our Mutual Friend is Charles Darwin. (2026-05-02T14:30:12.537Z - present)
    - The author of Our Mutual Friend is Charles Dickens. (date unknown - present)
    - Country Joe McDonald is a citizen of United States of America. (2026-0
  ```

**Zep pred answer**: `The author of *Our Mutual Friend* is Charles Dickens. Charles Dickens was married to Catherine Dickens, who is a citizen of the United Kingdom.`
**Zep EM**: ❌

---

### MH qid=1

**Question**: In which location did the spouse of Igor of Kiev pass away?

**Ground truth answer**: `Rodez`
**num_hops**: 2

#### Ground-truth has_pair chain (1 pairs):

- hop 1: old (seq 125): `Olga of Kiev died in the city of Kyiv.`
  → new (seq 450): `Olga of Kiev died in the city of Rodez.`

#### Mem0 history.db events touching these pairs:

**(none — Mem0 did NOT fire any UPDATE event for this pair)**

#### Mem0 retrieved (top of 100, only top-5 saved per qid) + answer:

- Igor of Kiev is married to Olga of Kiev
- Olga of Kiev died in Kyiv
- Gennady Rozhdestvensky died in the city of Moscow
- Nadezhda Krupskaya died in the city of Moscow
- Moscow is German

**Mem0 pred answer**: `The spouse of Igor of Kiev is Olga of Kiev, who died in Kyiv.`
**Mem0 EM**: ❌

#### Zep retrieved context preview + answer:

- edges=10, nodes=10, episodes=2
- preview (first 500 chars):

  ```
  
  FACTS and ENTITIES represent relevant context to the current conversation.
  
  # These are the most relevant facts and their valid date ranges. If the fact is about an event, the event takes place during this time.
  # format: FACT (Date range: from - to)
  
    - Igor of Kiev is married to Olga of Kiev. (2026-05-02T14:30:12Z - present)
    - Olga of Kiev died in the city of Kyiv. (date unknown - present)
    - Ursula K. Le Guin died in the city of Portland. (2018-03-01T00:00:00Z - present)
    - Oscar Wilde 
  ```

**Zep pred answer**: `The spouse of Igor of Kiev, Olga of Kiev, passed away in the city of Kyiv.`
**Zep EM**: ❌

---

### MH qid=5

**Question**: What is the name of the educational institution where the partner of Nicolae Ceaușescu was educated?

**Ground truth answer**: `Baldwin Wallace University`
**num_hops**: 2

#### Ground-truth has_pair chain (2 pairs):

- hop 0: old (seq 58): `Nicolae Ceaușescu is married to Elena Ceaușescu.`
  → new (seq 369): `Nicolae Ceaușescu is married to Wilhelm II.`
- hop 1: old (seq 349): `The univeristy where Wilhelm II was educated is University of Bonn.`
  → new (seq 453): `The univeristy where Wilhelm II was educated is Baldwin Wallace University.`

#### Mem0 history.db events touching these pairs:

- `ADD` [hop 0]: 
  - new_memory: `Nicolae Ceaușescu is married to Elena Ceaușescu`
- `UPDATE` [hop 0]: 
  - old_memory: `Nicolae Ceaușescu is married to Elena Ceaușescu`
  - new_memory: `Nicolae Ceaușescu is married to Wilhelm II`
- `ADD` [hop 0]: 
  - new_memory: `Nicolae Ceaușescu is married to Elena Ceaușescu`
- `UPDATE` [hop 0]: 
  - old_memory: `Nicolae Ceaușescu is married to Elena Ceaușescu`
  - new_memory: `Nicolae Ceaușescu is married to Wilhelm II`

#### Mem0 retrieved (top of 100, only top-5 saved per qid) + answer:

- Elena Ceaușescu was educated at University of Bucharest
- Nicolae Ceaușescu is married to Wilhelm II
- Headquarters of University of Bucharest is located in the city of Ankara
- Capital of Romania is Bucharest
- Leonte Răutu is employed by University of Bucharest

**Mem0 pred answer**: `Based on the provided information, Nicolae Ceaușescu is married to Wilhelm II, and Wilhelm II was educated at the University of Bonn. Therefore, the educational institution where the partner of Nicolae Ceaușescu was educated is the University of Bonn.`
**Mem0 EM**: ❌

#### Zep retrieved context preview + answer:

- edges=10, nodes=10, episodes=7
- preview (first 500 chars):

  ```
  
  FACTS and ENTITIES represent relevant context to the current conversation.
  
  # These are the most relevant facts and their valid date ranges. If the fact is about an event, the event takes place during this time.
  # format: FACT (Date range: from - to)
  
    - Nicolae Ceaușescu is married to Elena Ceaușescu. (2026-05-02T00:00:00Z - present)
    - The univeristy where Samuel Beckett was educated is Trinity College Dublin. (date unknown - present)
    - The univeristy where Samuel Beckett was educated is 
  ```

**Zep pred answer**: `The provided context does not contain information regarding the educational institution where Elena Ceaușescu (the partner of Nicolae Ceaușescu) was educated.`
**Zep EM**: ❌

---

### MH qid=9

**Question**: What is the location of work of the founder of the religion to which John Walsh belongs?

**Ground truth answer**: `Berlin`
**num_hops**: 3

#### Ground-truth has_pair chain (2 pairs):

- hop 0: old (seq 282): `John Walsh is affiliated with the religion of Catholic Church.`
  → new (seq 361): `John Walsh is affiliated with the religion of Methodism.`
- hop 1: old (seq 218): `Methodism was founded by John Wesley.`
  → new (seq 287): `Methodism was founded by Joseph Goebbels.`

#### Mem0 history.db events touching these pairs:

- `ADD` [hop 0]: 
  - new_memory: `John Walsh is affiliated with the religion of Catholic Church`
- `UPDATE` [hop 0]: 
  - old_memory: `John Walsh is affiliated with the religion of Catholic Church`
  - new_memory: `John Walsh is affiliated with Methodism`
- `ADD` [hop 0]: 
  - new_memory: `John Walsh is affiliated with the religion of Catholic Church`
- `UPDATE` [hop 0]: 
  - old_memory: `John Walsh is affiliated with the religion of Catholic Church`
  - new_memory: `John Walsh is affiliated with Methodism`
- `ADD` [hop 1]: 
  - new_memory: `Methodism was founded by John Wesley`

#### Mem0 retrieved (top of 100, only top-5 saved per qid) + answer:

- John Walsh is affiliated with Methodism
- Karen Armstrong is affiliated with the religion of Church of Scotland
- Methodism was founded by Joseph Goebbels
- Catholic Church was founded by Jesus Christ
- Boston was founded by John Winthrop

**Mem0 pred answer**: `John Walsh is affiliated with Methodism. According to the provided information, Methodism was founded by Joseph Goebbels, and Joseph Goebbels worked in the city of Berlin.`
**Mem0 EM**: ✅

#### Zep retrieved context preview + answer:

- edges=10, nodes=10, episodes=7
- preview (first 500 chars):

  ```
  
  FACTS and ENTITIES represent relevant context to the current conversation.
  
  # These are the most relevant facts and their valid date ranges. If the fact is about an event, the event takes place during this time.
  # format: FACT (Date range: from - to)
  
    - Methodism was founded by John Wesley. (2026-05-02T14:30:13.308Z - present)
    - Boston was founded by John Winthrop. (2026-05-02T14:30:12.118Z - present)
    - Church of Scotland was founded by John Knox. (date unknown - present)
    - John Keats d
  ```

**Zep pred answer**: `I am sorry, but I do not have information regarding the religion of John Walsh or the location of work for the founder of that religion.`
**Zep EM**: ❌

---

### MH qid=30

**Question**: What city or town is the headquarters of the educational institution, where the performer of the album "Blood on the Tracks" received education, located in?

**Ground truth answer**: `New York City`
**num_hops**: 3

#### Ground-truth has_pair chain (2 pairs):

- hop 0: old (seq 52): `Blood on the Tracks was performed by Bob Dylan.`
  → new (seq 181): `Blood on the Tracks was performed by Lou Reed.`
- hop 1: old (seq 286): `The univeristy where Lou Reed was educated is Syracuse University.`
  → new (seq 399): `The univeristy where Lou Reed was educated is Fordham University.`

#### Mem0 history.db events touching these pairs:

- `ADD` [hop 0]: 
  - new_memory: `Blood on the Tracks was performed by Bob Dylan`
- `UPDATE` [hop 0]: 
  - old_memory: `Blood on the Tracks was performed by Bob Dylan`
  - new_memory: `Blood on the Tracks was performed by Lou Reed`
- `ADD` [hop 0]: 
  - new_memory: `Blood on the Tracks was performed by Bob Dylan`
- `UPDATE` [hop 0]: 
  - old_memory: `Blood on the Tracks was performed by Bob Dylan`
  - new_memory: `Blood on the Tracks was performed by Lou Reed`

#### Mem0 retrieved (top of 100, only top-5 saved per qid) + answer:

- Berklee College of Music is headquartered in Boston
- Blood on the Tracks was performed by Lou Reed
- The headquarters of The University of the Arts is located in the city of Philadelphia
- The headquarters of Fordham University is located in the city of New York City
- Bob Dylan was educated at University of Minnesota

**Mem0 pred answer**: `Based on the provided information:

1.  The album "Blood on the Tracks" was performed by **Lou Reed**.
2.  Lou Reed was educated at **Fordham University**.
3.  The headquarters of Fordham University is located in **New York City**.`
**Mem0 EM**: ✅

#### Zep retrieved context preview + answer:

- edges=10, nodes=10, episodes=7
- preview (first 500 chars):

  ```
  
  FACTS and ENTITIES represent relevant context to the current conversation.
  
  # These are the most relevant facts and their valid date ranges. If the fact is about an event, the event takes place during this time.
  # format: FACT (Date range: from - to)
  
    - Blood on the Tracks was performed by Lou Reed. (2026-05-02T14:30:12Z - present)
    - Blood on the Tracks was performed by Bob Dylan. (2026-05-02T00:00:00Z - 2026-05-02T14:30:12Z)
    - The headquarters of University of Bucharest is located in the
  ```

**Zep pred answer**: `The performer of the album "Blood on the Tracks" is Bob Dylan. Bob Dylan was educated at the University of Minnesota, which is headquartered in the city of Minneapolis.`
**Zep EM**: ❌

---

### MH qid=50

**Question**: What is the place of death of the partner of the head of government of the Council of People's Commissars?

**Ground truth answer**: `Mansourah, Algeria`
**num_hops**: 3

#### Ground-truth has_pair chain (3 pairs):

- hop 0: old (seq 324): `The name of the current head of the Council of People's Commissars government is Vladimir Lenin.`
  → new (seq 351): `The name of the current head of the Council of People's Commissars government is Tony Blair.`
- hop 1: old (seq 141): `Tony Blair is married to Cherie Blair.`
  → new (seq 424): `Tony Blair is married to Alan Jay Lerner.`
- hop 2: old (seq 170): `Alan Jay Lerner died in the city of New York City.`
  → new (seq 394): `Alan Jay Lerner died in the city of Mansourah, Algeria.`

#### Mem0 history.db events touching these pairs:

- `ADD` [hop 0]: 
  - new_memory: `The current head of the Council of People's Commissars government is Vladimir Lenin`
- `UPDATE` [hop 0]: 
  - old_memory: `The current head of the Council of People's Commissars government is Vladimir Lenin`
  - new_memory: `Tony Blair is the head of the Council of People's Commissars government`
- `ADD` [hop 0]: 
  - new_memory: `The current head of the Council of People's Commissars government is Vladimir Lenin`
- `UPDATE` [hop 0]: 
  - old_memory: `The current head of the Council of People's Commissars government is Vladimir Lenin`
  - new_memory: `Tony Blair is the head of the Council of People's Commissars government`
- `ADD` [hop 1]: 
  - new_memory: `Tony Blair is married to Cherie Blair`

#### Mem0 retrieved (top of 100, only top-5 saved per qid) + answer:

- Tony Blair is the head of the Council of People's Commissars government
- Head of state in Soviet Union is Mikhail Gorbachev
- The chairperson of Congolese Party of Labour is Denis Sassou-Nguesso
- Chairperson of Fatah is Moshe Kahlon
- Narendra Modi is a citizen of Australia

**Mem0 pred answer**: `Based on the provided information:

1.  The head of the Council of People's Commissars government is **Tony Blair**.
2.  Tony Blair is married to **Cherie Blair**.
3.  There is no information provided regarding the place of death for Cherie Blair.`
**Mem0 EM**: ❌

#### Zep retrieved context preview + answer:

- edges=10, nodes=10, episodes=5
- preview (first 500 chars):

  ```
  
  FACTS and ENTITIES represent relevant context to the current conversation.
  
  # These are the most relevant facts and their valid date ranges. If the fact is about an event, the event takes place during this time.
  # format: FACT (Date range: from - to)
  
    - The name of the current head of state in Soviet Union is Mikhail Gorbachev. (date unknown - present)
    - The name of the current head of the Japan government is Shinzō Abe. (2026-05-02T14:30:13.308Z - present)
    - The name of the current head 
  ```

**Zep pred answer**: `Based on the provided facts, Nicolae Ceaușescu is married to Elena Ceaușescu. However, the provided context does not contain information regarding the place of death for Elena Ceaușescu.`
**Zep EM**: ❌

---

### SH qid=30

**Question**: Which country was baseball created in?

**Ground truth answer**: `Japan`

#### Ground-truth has_pair chain (1 pairs):

- old (seq 160): `baseball was created in the country of United States of America.`
  → new (seq 382): `baseball was created in the country of Japan.`

#### Mem0 history.db events touching these pairs:

**(none — Mem0 did NOT fire any UPDATE event for this pair)**

#### Mem0 retrieved (top of 100, only top-5 saved per qid) + answer:

- Baseball was created in Japan
- cricket was created in the country of England
- New Firm is associated with the sport of baseball
- Basketball was created in the Soviet Union
- Association football was created in the country of Italy

**Mem0 pred answer**: `Baseball was created in Japan.`
**Mem0 EM**: ✅

#### Zep retrieved context preview + answer:

- edges=10, nodes=10, episodes=10
- preview (first 500 chars):

  ```
  
  FACTS and ENTITIES represent relevant context to the current conversation.
  
  # These are the most relevant facts and their valid date ranges. If the fact is about an event, the event takes place during this time.
  # format: FACT (Date range: from - to)
  
    - baseball was created in the country of United States of America. (date unknown - present)
    - baseball was created in the country of Japan. (date unknown - present)
    - cricket was created in the country of England. (2026-05-02T00:00:00Z - 202
  ```

**Zep pred answer**: `Baseball was created in the United States of America and Japan.`
**Zep EM**: ✅

---

### SH qid=50

**Question**: Which continent is Bengaluru located in?

**Ground truth answer**: `Oceania`

#### Ground-truth has_pair chain (1 pairs):

- old (seq 4): `Bengaluru is located in the continent of Asia.`
  → new (seq 234): `Bengaluru is located in the continent of Oceania.`

#### Mem0 history.db events touching these pairs:

- `UPDATE`: 
  - old_memory: `Bengaluru is in Asia`
  - new_memory: `Bengaluru is located in the continent of Oceania`
- `UPDATE`: 
  - old_memory: `Bengaluru is in Asia`
  - new_memory: `Bengaluru is located in the continent of Oceania`

#### Mem0 retrieved (top of 100, only top-5 saved per qid) + answer:

- Bengaluru is located in the continent of Oceania
- India is located in the continent of Africa
- Australia is located in the continent of South America
- Canada is located in the continent of North America
- Germany is located in the continent of Europe

**Mem0 pred answer**: `Bengaluru is located in the continent of Oceania.`
**Mem0 EM**: ✅

#### Zep retrieved context preview + answer:

- edges=10, nodes=10, episodes=10
- preview (first 500 chars):

  ```
  
  FACTS and ENTITIES represent relevant context to the current conversation.
  
  # These are the most relevant facts and their valid date ranges. If the fact is about an event, the event takes place during this time.
  # format: FACT (Date range: from - to)
  
    - Bengaluru is located in the continent of Asia. (2026-05-02T00:00:00Z - present)
    - Bengaluru is located in the continent of Oceania. (date unknown - present)
    - India is located in the continent of Africa. (2026-05-02T00:00:00Z - 2026-05-02T
  ```

**Zep pred answer**: `Based on the provided context, Bengaluru is located in the continent of Asia (as well as Oceania, according to one of the facts).`
**Zep EM**: ✅

---
