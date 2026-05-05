# Valsts valodas pārbaudes simulators (Codex) - Lietotāja rokasgrāmata

## Saturs
1. [Quick Start (5 minūtes)](#quick-start-5-minūtes)
2. [Navigācijas karte](#navigācijas-karte)
3. [Īsti darbības plūsmas](#ķīsti-darbības-plūsmas)
4. [Admin/Super lietotāja sadaļa](#adminsuper-lietotāja-sadaļa)
5. [Pārkļuvesīšanas vadīklas](#pārkļuvesīšanas-vadīklas)
6. [Atrumiņkarte](#atrumiņkarte)

---

## Quick Start (5 minūtes)

1. **Sākumu uzdevums**
   - Atveriet pārlūkprogrammu un pārejiet uz `http://localhost:4173` (vai jūsu servera adresi)
   - Sadaļā **Exam** (eksāms) atlasiet "A2 Mock Exam 01" no izvēlnes
   - Nospiediet pogu **Submit Answers** (Iesniegt atbildes) sākot eksāma simulāciju
   - Aizpildiet visus uzdevumus (klausīšanās, lasīšanās, rakstīšana, runāšana)
   - Kad esat gatavi, nospiediet **Submit Answers** zemākajā kreisajā stūrī

2. **Aizsūtnes apskatīšana**
   - Pēc iesniegšanas pāriet uz cilni **Submission** (Iesniegums)
   - Skatiet savas atbildes un kopējiem punktiem
   - Lai saņemtu AI vērtējumu, nospiediet **AI Score** (AI ērtējs) pogu

3. **Rezultātu skatīšana**
   - Pēc AI vērtējuma pāriet uz cilni **Quality** (Kvalitāte)
   - Skatiet punktus katrā prasmē un kopējo rezultātu
   - Pārbaudiet, vai esat pārzeijuši (nepieciešams visās prasmēs: 9/15 punkti katrā)

---

## Navigācijas karte

Galvenais izkārtojums consist no kreisas paneļa (navigācija) un vidējās darbvietas (saturs).

### Kreisais panels (pogas)
- **Dashboard** (Instrumentpanelis) – skats uz jūsu statistiku, pēdējiem mēģinājumiem un brīvdienu statusu
- **Exams** (Eksāmi) – saraksts ar pieejamajiem eksāmiem (A2 Mock Exam 01, 02, u.c.)
- **Admin** (Administrēšana) – lietotāju un sistēmas iestatījumi (tikai superlietotājiem)
- **Runner** (Izpildītājs) – vieta, kur veicāt eksāma simulāciju (noklusējuma skats)
- **Submission** (Iesniegums) – skatīt savas iesniegtās atbildes pēc eksāma
- **Billing** (Maksājumi) – pārbaudīt abonementu, nopirkt papildus piekļuvi vai AI kredītus
- **Markdown** – skatīt eksāma avotu (.md fails)
- **JSON** – skatīt eksāma datus (JSON formātā)
- **TTS** – klausīties teksta uz ljudu pārveidojumu (piesārņojumiem)
- **Prompts** – skatīt attēlus runāšanas daļai
- **Quality** (Kvalitāte) – AI vērtējuma rezultāti un atsauksmes

### Vidējā darbvieta
Mainīgs atkarībā no atlasītās pogas kreisajā panelī. Parādās forma, teksts, diagrammas vai citi elementi.

---

## Īsti darbības plūsmas

### Sāk jaunu eksāma mēģinājumiem
1. Kreisajā panelī nospiedziet **Runner** (Izpildītājs)
2. Laukā **Exam** (Eksāms) atlasiet vajadzīgo eksāmu (piemēram, "A2 Mock Exam 01")
3. Laukā **Source Markdown** (Avota Markdown) redzīsim, kurš fails tiks izmantots
4. Nospiediet **Submit Answers** (Iesniegt atbildes) – sāksies laika mērīšana
5. Aizpildiet visas sekcijas (klausīšanās, lasīšanās, rakstīšana, runāšana)
6. Kad esat gatavi, atkārtoti nospiediet **Submit Answers** zemākajā kreisajā stūrī
7. Pēc iesniegšanas pāriet uz **Submission** vai **Quality** lai skatītu rezultātus

### Atcelt mēģinājumu (resume an attempt)
> Piezīme: Šis simulātors neiespējo saglabā nepabeigtu mēģinājumu. Jaat Albert atsācies, jums ir jāsāk no jauna.
> Ja jūs vēlaties sākt vienādu eksāmu no jauna:
> 1. Atlasiet to pašu eksāmu lauākā **Exam**
> 2. Nospiediet pogu **Reload** (Atjaunot) – NOTIRA visu ievadīto
> 3. Sācip jaunu mēģinājumu kā jau aprakstīts augstāk

### Pārbaudiet jūsu piekļuves statusu (entitlements)
1. Kreisajā panelī nospiedziet **Billing** (Maksājumi)
2. Skatiet zemāko bloku **Your Entitlements** (Jūsu piekļuves tiesības)
   - **Free attempts remaining** – brīvie mēģinājumi šodien
   - **Paid attempts remaining** – maksājieši mēģinājumi jūsu abonementā
   - **AI credits remaining** – atlikušie AI vērtējuma kredīti
   - **Subscription status** – abonementa tips (Free, Pro, Enterprise, u.c.) un beigu datums
3. Ja redzāt **Frozen** (Blokēts), jūsu konts ir blokēts maksājuma vai kredīta problēmu dēļ

### Iepirkojiet piekļuvi (Single Exam, Exam Pack, Subscription, AI Scoring Credits)
1. Kreisajā panelī nospiedziet **Billing** (Maksājumi)
2. Sadaļā **Purchase options** (Pirkšanas opcijas) izvēlieties:
   - **Single Exam** – vienreizējs piekļuves vienam konkrētam eksāmam
   - **Exam Pack** – paketis vairākiem eksāmiem (piemēram, 5 eksāmi)
   - **Subscription** – mēneša abonementu (piemēram, Pro plaņs ar neierobežotu eksāmu skaitu)
   - **AI Scoring Credits** – papildu kredīti AI vērtēšanai (ja jūsu plaņs ietvertā kvota nav pietiekama)
3. Nospiediet pogu **Buy** (Pirkt) izvēlētajam produktam
4. Sekojiet Stripe maksājuma instrukcijām (ievadiet kartes datus vai izmantojiet risinājumu)
5. Pēc veiksmīga maksājuma jūsu tiesības tiks atjaunotas automātiski

### Ierakstiet/verifikējiet AI vērtēšanu un interpretējiet izni
1. Pēc eksāma iesniegšanas (skatiet "Sāk jaunu eksāma mēģinājumiem" augstāk)
2. Kreisajā panelī nospiedziet **AI Score** (AI ērtējs) – ja pogas nav, tā nozīmē, ka jūs vēlaties AI vērtēšanu
3. Pārbaudiet, vai jums pietiek AI kredīti:
   - Ja redzāt paziņojumu **"AI credits remaining: 0"**, jums ir jāpirk papildus kredītus vai gaidīt, kamēr atjaunošas dieniskas kvotas
4. Pēc ka AI vērtējums ir beidzies:
   - Pāriet uz cilni **Quality** (Kvalitāte)
   - Skatiet:
     - Kopējo punktu skaitu (maksimāls 60)
     - Punktus katrā prasmē (klausīšanās, lasīšanās, rakstīšana, runāšana) – katrai nepieciešams vismaz 9/15
     - Detalizētās atsauksmes katrai uzdevuma grupai (piemēram, "Rakstīšana: Uzdevums 1 – labi strukturēts, bet vajag vairāk precīzās leksikas")
   - Ja visās prasmeš ir vismaz 9/15 punktu, esat pārzeijuši. Citādāk, skatiet, kur jums vajag uzlabot

---

## Admin/Super lietotāja sadaļa

### Ko nozīmē "pilna piekļuve" (full access)
Superlietotājam (admin) jābūt pieejām:
- Neierobežots eksāmu mēģinājumu skaits (brīvie un maksājieši)
- Neierobežots AI vērtējuma kredītu skaits
- Piekļuve Admin panelim (lietotāju pārvaldība, sistēmas iestatījumi)
- Spēja skatīt visus lietotājus un to statistiku
- Spēja anulēt vai izmainīt kādu lietotāju abonementu

### Kde apstiprināt jūsu lomu un tiesības
1. Kreisajā panelī nospiedziet **Admin** (Administrēšana)
2. Ja redzāt sadaļu **User Management** (Lietotāju pārvaldība) vai **System Settings** (Sistēmas iestatījumi), jūs esat admin
3. Alternatīvi, pāriet uz **Billing** → skatiet **Subscription status** – ja redzāt "admin" vai "unlimited", jums ir pilna piekļuve
4. Ja ne redzāt Admin pogu vai to sadaļas ir tukša, sazinieties ar sistēmas administratoru vai pārbaudiet datubāzi

### Pārkļuvesīšanas kontrola saraksts, kad AI vērtējums rāda "credits remaining: 0"
1. Pārbaudiet abonementa statusu:
   - **Billing** → **Subscription status** – vai jūs esat Free, Pro, Enterprise vai admin plaņa?
   - Ja esat Free plaņa, jums ir limite (piemēram, 3 AI vērtējumi dienā)
2. Pārbaudiet dieniskas lietojuma statistiku:
   - Ja esat izmantojis visus dieniskos AI kredītus, jums ir jāgaidīt līdz nākamai dienai vai pirkt papildus kredītus
3. Pārbaudiet, vai nav maksājuma problēma:
   - Ja jūs recenti pirkojāt kredītus, bet tās netiek rādītas, pārbaudiet Stripe vesturiku vai sazinieties ar atbalstu
4. Ja esat admin un vēl redzat kredītu trūkumu:
   - Pāriet uz **Admin** → **System Settings** → **AI Scoring Limits** un pārbaudiet, vai jūsu plaņa limits nav nastavits uz 0
   - Ja esat paškopēji mainījusi iestatījumus, atjaunojiet uz noklusējuma vai maksimālo vērtību
5. Ja viss cits šķiet pareizi, bet problēma pastāv:
   - Atjaunojiet lapu (Ctrl+F5 vai Cmd+Shift+R)
   - Iztīriet pārlūka kešmāti vai mēģiniet ar citu pārlūkprogrammu
   - Ja problēma pastāv, sazinieties ar tehnisko atbalstu ar detalizētu aprakstu un ekrānuzņēmumu

---

## Pārkļuvesīšanas vadīklas (simptomi → causes → fixes)

| Simptoms                                      | Iemesli                                              | Risinājumi                                                                 |
|-----------------------------------------------|------------------------------------------------------|----------------------------------------------------------------------------|
| **free_exhausted**                            | Izmantoti visi brīvie mēģinājumi šodien (3 dienā)   | Gaidiet līdz nākamai dienai vai aprieciet abonementu papildus mēģinājumiem |
| **Paid attempts remaining: 0**                | Izmantoti visi maksājieši mēģinājumu abonementā      | Pirkojiet papildus eksāmu paketi vai pāriet uz abonementu ar vairāk mēģinājumiem |
| **AI credits remaining: 0**                   | Izmantoti visi dieniskie AI vērtējuma kredīti        | Gaidiet līdz nākamai dienai, pirkojiet papildus AI kredītus vai pārinspectējiet abonementu plaņu |
| "You have used the free exam…" (Jūs esat izmantojis brīvu eksāmu…) | Bandis mēģināt eksāmu, kas nav pieejams brīvi       | Izmanto vienu no brīvajiem mēģinājumiem vai pāriet uz maksājamo opciju (Single Exam, Exam Pack, Abonementu) |

---

## Atrumiņkarte

| Darbība                                 | Kur atrast un ko nospiezt                                                                 |
|-----------------------------------------|-------------------------------------------------------------------------------------------|
| Sākt jaunu eksāmu                      | **Runner** → atlasiet eksāmu → **Submit Answers** (sākums)                                |
| Iesniegt atbildes                       | Katrā sekcijā aizpildot → zemākajā kreisajā stūrī → **Submit Answers**                    |
| Skatīt iesniegumu                       | Pēc iesniegšanas → **Submission**                                                         |
| Saņemt AI vērtējumu                     | Pēc iesniegšanas → **AI Score**                                                           |
| Skatīt AI rezultātus                    | Pēc AI vērtējuma → **Quality**                                                            |
| Pārbaudiet brīvus mēģinājumus           | **Billing** → **Free attempts remaining**                                                |
| Pārbaudiet maksājamos mēģinājumus       | **Billing** → **Paid attempts remaining**                                                |
| Pārbaudiet AI kredītus                  | **Billing** → **AI credits remaining**                                                    |
| Pirkt vienkāršu eksāmu                  | **Billing** → **Purchase options** → **Single Exam** → **Buy**                           |
| Pirkt eksāmu paketi                     | **Billing** → **Purchase options** → **Exam Pack** → **Buy**                              |
| Pirkt abonementu                        | **Billing** → **Purchase options** → **Subscription** → **Buy**                           |
| Papildus AI kredīti                     | **Billing** → **Purchase options** → **AI Scoring Credits** → **Buy**                     |
| Pāriet uz admin panelī                  | **Admin** (tikai ja esat superlietotājs)                                                 |
| Atjaunot eksāmu (ja kļūda)              | Kreisajā panelī → **Reload**                                                              |
| Kopēt atbildes tekstu                   | Pēc iesniegšanas → **Submission** → **Copy Submission**                                   |
| Saglabāt atbildes                      | Pēc iesniegšanas → **Submission** → **Download Submission** (vai .md/.json)               |