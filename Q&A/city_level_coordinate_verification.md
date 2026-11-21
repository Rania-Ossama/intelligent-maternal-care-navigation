# City-Level and District Coordinate Truth Audit Report (N = 798)

## 1. Executive Summary

To eliminate the "City A vs. City B" coordinate bug (where a hospital physically located in City A has GPS coordinates landing in City B, in a desert fallback, or with inverted latitude/longitude), all **798 facilities** in `facilities_sorted_by_governorate.csv` were audited across four independent verification layers:

1. **District Centroid & Haversine Distance Check**: Checked every facility against ~75 Upper Egypt `markaz` and city centroids.
2. **English & Arabic Name-to-City Extraction + Google Plus Code Decoding**: Verified Plus Codes embedded in street addresses and tested for swapped `(latitude, longitude)` pairs.
3. **Live Multi-API Reverse Geocoding (100% Coverage)**: Reverse-geocoded all 720 unique coordinate pairs (798 records) via **ArcGIS World GeocodeServer** and **BigDataCloud Reverse Geocode Client**.
4. **Live Multi-API Forward Geocoding & Rooftop Correction**: Resolved every verified discrepancy using **ArcGIS `findAddressCandidates`**, **Photon (Komoot)**, and verified rooftop records, then re-verified every modified pin via live reverse geocoding.

### Post-Fix Verification Distribution (N = 798)

| City Match Status | Facility Count | Percentage |
| :--- | :---: | :---: |
| 100% Verified Same City | 755 | 94.61% |
| 100% Verified Same City (District Label Corrected) | 19 | 2.38% |
| Corrected from City B to City A (100% Verified Same City) | 16 | 2.01% |
| Verified True GPS - Quarantined Out-of-Upper-Egypt (Atfeeh, Giza) | 4 | 0.50% |
| Corrected (Unswapped Lat/Lon) - Quarantined Out-of-Upper-Egypt (Marsa Matrouh) | 3 | 0.38% |
| Non-Clinical Summary Row (Excluded from Routing) | 1 | 0.13% |

- **Total Active Upper Egypt Facilities Verified in True City/District**: **790 / 790 (100.00%)** (`755` already verified in true city + `16` Upper Egypt coordinates corrected from City B to City A + `19` district labels aligned to match their verified rooftop GPS). Plus `1` non-clinical summary row (`CE00130`, excluded from routing) and `7` quarantined Out-of-Upper-Egypt rows = **798 total records**.
- **Quarantined Out-of-Upper-Egypt Facilities (`OUT_OF_BOUNDS`)**: **7 rows** (3 Marsa Matrouh North Coast hospitals whose swapped `lat`/`lon` were fixed so they now map accurately to El Alamein/North Coast + 4 Giza Atfeeh border hospitals). Note: `CE01635` (Al Atamin Specialized Charity Hospital) has verified GPS in Qus, Qena.
- **Missing Data Across All Columns**: **0.00%** across all 4 synchronized datasets (`facilities_sorted_by_governorate.csv`, `hospital_validation.csv`, `coordinate_and_missing_data_flags.csv`, and `final_maternal_facilities_clean.csv`).

---

## 2. All 19 Verified Coordinate Corrections (Before vs. After Proof Table)

| ID | Facility Name | Governorate / District | Old GPS (City B / Wrong) | New Verified GPS (City A / True) | Shift (km) | Post-Fix ArcGIS Reverse Geocode Confirmation |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| `CE00245` | Andalusia Hospitals North Coast | Beni Suef / El Alamein | `28.740171, 30.973718` | `30.973718, 28.740171` | 328.73 | مطروح / قسم العلمين (سيدي عبد الرحمن, قسم العلمين, مطروح) |
| `CE00256` | Marina Central Hospital | Beni Suef / North Coast | `29.027790, 30.822634` | `30.822634, 29.027790` | 264.09 | مطروح / قسم مارينا العلمين السياحيه (مارينا العلمين السياحيه, قسم مارينا العلمين السياحيه, مطروح) |
| `CE00260` | AAST-MT ALAMEIN HOSPITAL | Beni Suef / El Alamein | `28.880264, 30.828330` | `30.828330, 28.880264` | 286.72 | مطروح / قسم العلمين (تل العيس, قسم العلمين, مطروح) |
| `CE00588` | Iman Hospital | Minya / Beni Mazar | `28.917875, 30.853829` | `28.493006, 30.807582` | 47.46 | المنية / مركز بنى مزار (3 حارة توما, بني مزار, مركز بنى مزار, المنية) |
| `CE00054` | Beni Suef General | Beni Suef / Beni Suef | `29.025872, 31.099101` | `29.064190, 31.102960` | 4.28 | بنى سويف / قسم بنى سويف (فوزي, بني سويف, قسم بنى سويف, بنى سويف, 62111) |
| `CE01979` | Al Ghanayem Al Markazi | Assiut / El Ghanayem | `27.100000, 31.210000` | `26.885476, 31.320177` | 26.23 | اسيوط / مركز الغنايم (مستشفى الغنائم المركزي) |
| `CE01980` | Sahel Selim Central Hospital | Assiut / Sahel Selim | `26.990000, 31.470000` | `27.064249, 31.350461` | 14.43 | اسيوط / مركز ساحل سليم (23 يوليو, ساحل سليم, مركز ساحل سليم, اسيوط, 71723) |
| `CE01976` | Sidfa Central Hospital | Assiut / Sodfa | `27.174000, 31.388000` | `26.964901, 31.383349` | 23.26 | اسيوط / مركز صدفا (الجيش, صدفا, مركز صدفا, اسيوط, 71748) |
| `CE01981` | Dar El Salam Central Hospital | Sohag / Dar El Salam | `26.410000, 31.720000` | `26.279193, 32.058060` | 36.69 | سوهاج / مركز دار السلام (محطة البنزين) |
| `CE01978` | Tima Central Hospital | Sohag / Tima | `26.917000, 31.417000` | `26.896842, 31.442093` | 3.35 | سوهاج / مركز طما (أحمد عرابي, طما, مركز طما, سوهاج) |
| `CE00087` | Akhmim Central Hospital | Sohag / Akhmim | `26.539883, 31.782745` | `26.562324, 31.729882` | 5.82 | سوهاج / مركز اخميم (250, مركز اخميم, سوهاج, 82714) |
| `CE00085` | Al Monshaah Central Hospital | Sohag / Al Monshaah | `26.479882, 31.800675` | `26.479869, 31.797291` | 0.34 | سوهاج / مركز المنشـــاه (عبد المنعم رياض, مركز المنشـــاه, سوهاج) |
| `CE00088` | Al Maragha Central Hospital | Sohag / Al Maragha | `26.703738, 31.605436` | `26.700493, 31.600726` | 0.59 | سوهاج / مركز المراغه (مستشفى المراغة المركزي) |
| `CE00089` | Awlad Hamza Central Hospital | Sohag / Al Usayrat | `26.392551, 31.820737` | `26.393611, 31.822828` | 0.24 | سوهاج / مركز العسيرات (أولاد حمزة - مقر المركز, مركز العسيرات, سوهاج) |
| `CE02000` | Dar AlShifa Hospital | Sohag / Tahta | `26.574569, 31.695078` | `26.763978, 31.504423` | 28.33 | سوهاج / قسم طهطا (مستشفى دار الشفاء) |
| `CE00106` | Al Waqf Central Hospital | Qena / Al Waqf | `26.108000, 32.411000` | `26.091816, 32.425893` | 2.33 | قنا / مركز الوقف (المستشفى, الوقف, مركز الوقف, قنا) |
| `CE01942` | Central Waqf Hospital | Qena / Al Waqf | `26.108000, 32.411000` | `26.091816, 32.425893` | 2.33 | قنا / مركز الوقف (المستشفى, الوقف, مركز الوقف, قنا) |
| `CE01553` | Kaft Teaching Hospital | Qena / Qift | `26.155061, 32.716012` | `25.995891, 32.810306` | 20.05 | قنا / مركز قفط (الجيش, قفط, مركز قفط, قنا, 83729) |
| `CE00013` | University Hospital - Luxor University (under construction) | Luxor / New Thebes | `25.687200, 32.639600` | `25.739507, 32.761954` | 13.57 | الأقصر / مركز طيبه (مدخل طيبة, طيبة, مركز طيبه, الأقصر, 83911) |

---

## 3. All 19 District Label & Metadata Alignments (GPS Already Verified in True City)

| ID | Facility Name | Governorate | Updated District | Verification Note |
| :--- | :--- | :--- | :--- | :--- |
| `CE00049` | Ahansiya Specialized Hospital | Beni Suef | Ihnasya | GPS verified in Ihnasya (district previously listed governorate capital Beni Suef) |
| `CE00158` | Nasser Central Hospital | Beni Suef | Nasser | GPS verified in Nasser (district previously listed governorate capital Beni Suef) |
| `CE01924` | Al Adwa General Hospital | Minya | El Idwa | GPS verified in El Idwa (district previously listed governorate capital Minya) |
| `CE01925` | Al-Arwa Documentary Hospital | Minya | Abu Qurqas | GPS verified in Abu Qurqas (district and synthetic address previously listed Minya City) |
| `CE01926` | Intellectual General Hospital | Minya | Abu Qurqas | GPS verified in Abu Qurqas (district and synthetic address previously listed Minya City) |
| `CE01927` | The good shepherd. | Minya | Samalut | GPS verified in Samalut matching CE00708/CE00674 (district and synthetic address previously listed Minya City) |
| `CE01990` | Martyr Abdul Moneim Riad Al-Jadida Hospital | Sohag | Sohag | GPS verified in First Department of Sohag on Al-Jergawiya St. (street name tricked raw district to Girga) |
| `CE01006` | Abou Tesht Central Hospital | Qena | Abu Tesht | GPS verified in Abu Tesht (district previously listed Qena) |
| `CE01950` | Nile Naqada Hospital | Qena | Naqada | GPS verified in Naqada (district previously listed Qena) |
| `CE01951` | Luxor International Hospital | Luxor | Luxor | GPS verified in Luxor City (legacy district still listed Qena) |
| `CE01952` | Luxor Medical Center | Luxor | Luxor | GPS verified in Luxor City (legacy district still listed Qena) |
| `CE00021` | Taibah Specialized Hospital (ISNA) | Luxor | Esna | GPS verified in Esna (district previously listed governorate capital Luxor) |
| `CE00022` | Horus Specialist Hospital (Erment) | Luxor | Armant | GPS verified in Armant (district previously listed governorate capital Luxor) |
| `CE01773` | Tod Central Hospital | Luxor | Al Tod | GPS verified in Al Tod (district previously listed Luxor) |
| `CE00036` | Al Kashef Specialized Hospital | Aswan | Edfu | GPS verified in Al-Radisiya Bahri, Edfu by ArcGIS + web directories (district and address updated from Aswan to Edfu) |
| `CE00045` | Almanar Hospital | Aswan | Edfu | GPS verified in Edfu by ArcGIS + UHIA/GAHAR records; removed stray <g id="1"> XML tag and corrected district/address to Edfu |
| `CE00039` | Kom Ombo Hospital | Aswan | Kom Ombo | GPS verified in Kom Ombo (district previously listed governorate capital Aswan) |
| `CE00040` | Abu Simbel International Hospital | Aswan | Abu Simbel | GPS verified in Abu Simbel (district previously listed governorate capital Aswan) |
| `CE00048` | Abu Simbel Hospital | Aswan | Abu Simbel | GPS verified in Abu Simbel (district previously listed governorate capital Aswan) |

---

## 4. Synchronized Output Artifacts

- `datasets/facilities_sorted_by_governorate.csv` (798 rows, 34 columns, 0.00% missing)
- `Q&A/hospital_validation.csv` (798 rows, 25 columns, 0.00% missing)
- `Q&A/coordinate_and_missing_data_flags.csv` (798 rows, 16 columns, 0.00% missing)
- `repo_work/final_maternal_facilities_clean.csv` (798 rows, 24 columns, 0.00% missing)
- `Q&A/city_level_coordinate_verification.csv` (798 rows, 14 columns)
- `Q&A/city_level_coordinate_verification.md` (this report)
- `coordinate_verifier_tool.html` (rebuilt with all 19 coordinate fixes and 19 district alignments embedded)