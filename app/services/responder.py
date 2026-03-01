import re

from app.models import ChatResponse, SourceItem
from app.services.diseases import DiseaseService
from app.services.hospitals import HospitalLocator, HospitalLookupError
from app.services.localization import t
from app.services.pregnancy import PregnancyService
from app.services.retriever import KnowledgeRetriever, KnowledgeDocument
from app.services.schemes import SchemeService
from app.services.triage import assess_triage


RESPONSE_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "for",
    "to",
    "of",
    "in",
    "on",
    "with",
    "my",
    "me",
    "i",
    "am",
    "is",
    "are",
    "what",
    "how",
    "why",
    "can",
    "should",
    "please",
    "about",
    "need",
    "help",
    "have",
    "has",
    "had",
    "this",
    "that",
    "it",
    "from",
}

PINCODE_PATTERN = re.compile(r"\b[1-9][0-9]{5}\b")
AGE_PATTERN = re.compile(r"\b(?:age\s*)?(\d{1,3})\s*(?:years?|yrs?|year old|year-old|yo|y/o)\b", re.IGNORECASE)

GOVERNMENT_HOSPITAL_MARKERS = {
    "government",
    "govt",
    "district hospital",
    "civil hospital",
    "medical college",
    "aiims",
    "cg",
    "phc",
    "chc",
}

SPECIALTY_HINTS = {
    "cancer": "Oncology",
    "oncology": "Oncology",
    "cardiac": "Cardiology",
    "heart": "Cardiology",
    "neuro": "Neurology",
    "ortho": "Orthopedics",
    "pediatric": "Pediatrics",
    "children": "Pediatrics",
    "maternity": "Obstetrics & Gynecology",
    "women": "Obstetrics & Gynecology",
    "eye": "Ophthalmology",
    "ent": "ENT",
    "kidney": "Nephrology/Urology",
    "renal": "Nephrology/Urology",
    "trauma": "Emergency/Trauma",
    "emergency": "Emergency/Trauma",
}

SECTION_TEXT = {
    "en": {
        "medical_section": "MEDICAL GUIDANCE SECTION",
        "hospital_section": "HOSPITAL FINDER SECTION (India Only)",
        "condition_overview": "1. Condition Overview",
        "age_group_impact": "2. How it affects this age group",
        "treatment": "3. Common treatment approaches (categories only)",
        "medicine": "4. Medicine types commonly used (no dosage)",
        "lifestyle": "5. Lifestyle recommendations",
        "avoid": "6. What to avoid",
        "warnings": "7. Warning signs requiring emergency care",
        "mental_support": "8. Emotional and mental health support advice",
        "med_intro": "- Medicines commonly used (doctor-guided):",
        "categories_line": "- Categories: clinical evaluation, doctor-guided medicines, monitoring, specialist referral if needed.",
        "emotional_extra": "- Speak with a qualified doctor/counsellor if fear, stress, or low mood is persistent.",
        "method_line": "Method: Input location/pincode → latitude/longitude → Haversine distance → nearest-first sorting.",
        "top_hospitals": "Top 5 nearest hospitals:",
        "emergency_note": "Emergency note: Critical symptoms detected. Please proceed immediately to the nearest emergency-capable hospital.",
        "detected_age_group": "- Age group identified:",
        "contact_na": "Not available",
        "hospital_unavailable": "Hospital lookup is temporarily unavailable. Please call 108 or visit the nearest PHC/government hospital immediately.",
        "hospital_name": "Hospital Name",
        "hospital_type": "Type",
        "hospital_specialty": "Specialty",
        "hospital_address": "Full Address",
        "hospital_pincode": "Pincode",
        "hospital_distance": "Distance in KM",
        "hospital_contact": "Contact",
        "no_hospital_name": "Unnamed Hospital",
        "no_hospital_address": "Address details not available",
        "hospital_type_government": "Government",
        "hospital_type_private": "Private",
        "specialty_general": "General",
        "age_child_impact": "{condition_name} in children can progress quickly due to lower physiological reserve; early pediatric review is important.",
        "age_teen_impact": "{condition_name} in teens may affect growth, school performance, and emotional wellbeing; age-appropriate counselling helps.",
        "age_elderly_impact": "{condition_name} in older adults can worsen faster with comorbidities (diabetes/BP/heart/kidney disease), so close monitoring is needed.",
        "age_adult_impact": "{condition_name} in adults may affect daily function and work capacity; timely diagnosis improves outcomes.",
        "low_info_need_details": "I need a little more detail to give safe and useful guidance for {topic}.",
        "low_info_share_details": "Share symptoms, duration, age, and known conditions (for example diabetes, pregnancy, BP).",
        "low_info_describe_step": "Describe your main symptom and duration clearly (example: '{query}').",
        "low_info_age_step": "Mention age, pregnancy status, chronic diseases, and current medicines.",
        "next_step_fever": "Track fever/breathing symptoms every 6-8 hours and keep hydration adequate.",
        "next_step_diabetes": "Check sugar/BP readings regularly and carry the log to your next clinic visit.",
        "next_step_pregnancy": "If pregnant, keep ANC visits on schedule and seek urgent care for bleeding or reduced fetal movement.",
    },
    "hi": {
        "medical_section": "चिकित्सीय मार्गदर्शन अनुभाग",
        "hospital_section": "अस्पताल खोज अनुभाग (केवल भारत)",
        "condition_overview": "1. स्थिति का सार",
        "age_group_impact": "2. इस आयु समूह पर प्रभाव",
        "treatment": "3. सामान्य उपचार दृष्टिकोण (केवल श्रेणियाँ)",
        "medicine": "4. आम दवा प्रकार (कोई डोज नहीं)",
        "lifestyle": "5. जीवनशैली सुझाव",
        "avoid": "6. किन बातों से बचें",
        "warnings": "7. आपातकालीन चेतावनी संकेत",
        "mental_support": "8. भावनात्मक और मानसिक स्वास्थ्य समर्थन",
        "med_intro": "- आम दवाएँ (केवल डॉक्टर की सलाह से):",
        "categories_line": "- श्रेणियाँ: क्लिनिकल मूल्यांकन, डॉक्टर-निर्देशित दवाएँ, मॉनिटरिंग, आवश्यकता होने पर विशेषज्ञ रेफरल।",
        "emotional_extra": "- डर, तनाव या उदासी बनी रहे तो योग्य डॉक्टर/काउंसलर से सलाह लें।",
        "method_line": "विधि: स्थान/पिनकोड इनपुट → अक्षांश/देशांतर → Haversine दूरी → निकटतम क्रम में परिणाम।",
        "top_hospitals": "निकटतम 5 अस्पताल:",
        "emergency_note": "आपातकालीन नोट: गंभीर लक्षण पहचाने गए हैं। कृपया तुरंत निकटतम आपातकालीन अस्पताल जाएँ।",
        "detected_age_group": "- पहचाना गया आयु समूह:",
        "contact_na": "उपलब्ध नहीं",
        "hospital_unavailable": "अस्पताल खोज अभी अस्थायी रूप से उपलब्ध नहीं है। कृपया 108 पर कॉल करें या तुरंत निकटतम PHC/सरकारी अस्पताल जाएँ।",
        "hospital_name": "अस्पताल का नाम",
        "hospital_type": "प्रकार",
        "hospital_specialty": "विशेषता",
        "hospital_address": "पूरा पता",
        "hospital_pincode": "पिनकोड",
        "hospital_distance": "दूरी (किमी)",
        "hospital_contact": "संपर्क",
        "no_hospital_name": "अस्पताल का नाम उपलब्ध नहीं",
        "no_hospital_address": "पते का विवरण उपलब्ध नहीं",
        "hospital_type_government": "सरकारी",
        "hospital_type_private": "निजी",
        "specialty_general": "सामान्य",
        "age_child_impact": "बच्चों में {condition_name} कम शारीरिक रिज़र्व के कारण जल्दी बढ़ सकता है; जल्दी बाल रोग विशेषज्ञ की सलाह जरूरी है।",
        "age_teen_impact": "किशोरों में {condition_name} बढ़वार, पढ़ाई और मानसिक स्वास्थ्य पर असर डाल सकता है; आयु-उपयुक्त परामर्श मदद करता है।",
        "age_elderly_impact": "वृद्धों में {condition_name} अन्य रोगों (डायबिटीज/BP/हृदय/किडनी) के साथ तेजी से बिगड़ सकता है; नज़दीकी निगरानी जरूरी है।",
        "age_adult_impact": "वयस्कों में {condition_name} रोज़मर्रा के काम और कार्यक्षमता पर असर डाल सकता है; समय पर जाँच से बेहतर परिणाम मिलते हैं।",
        "low_info_need_details": "{topic} के लिए सुरक्षित और उपयोगी मार्गदर्शन देने हेतु मुझे थोड़ी और जानकारी चाहिए।",
        "low_info_share_details": "कृपया लक्षण, अवधि, उम्र और ज्ञात बीमारियाँ (जैसे डायबिटीज, गर्भावस्था, BP) बताएं।",
        "low_info_describe_step": "मुख्य लक्षण और अवधि स्पष्ट लिखें (उदाहरण: '{query}').",
        "low_info_age_step": "उम्र, गर्भावस्था स्थिति, पुरानी बीमारियाँ और चल रही दवाइयाँ बताएं।",
        "next_step_fever": "हर 6-8 घंटे में बुखार/सांस के लक्षण नोट करें और पर्याप्त पानी लें।",
        "next_step_diabetes": "शुगर/BP नियमित जांचें और अगली विज़िट में रिकॉर्ड साथ ले जाएँ।",
        "next_step_pregnancy": "यदि गर्भवती हैं तो ANC विज़िट समय पर रखें और रक्तस्राव या भ्रूण की हलचल कम होने पर तुरंत देखभाल लें।",
    },
    "ta": {
        "medical_section": "மருத்துவ வழிகாட்டல் பகுதி",
        "hospital_section": "மருத்துவமனை கண்டறிதல் பகுதி (இந்தியா மட்டும்)",
        "condition_overview": "1. நிலையின் சுருக்கம்",
        "age_group_impact": "2. இந்த வயது குழுவில் தாக்கம்",
        "treatment": "3. பொதுவான சிகிச்சை அணுகுமுறைகள் (வகைகள் மட்டும்)",
        "medicine": "4. பொதுவாக பயன்படுத்தப்படும் மருந்து வகைகள் (அளவு இல்லை)",
        "lifestyle": "5. வாழ்க்கை முறை பரிந்துரைகள்",
        "avoid": "6. தவிர்க்க வேண்டியது",
        "warnings": "7. அவசர சிகிச்சை தேவைப்படும் எச்சரிக்கை அறிகுறிகள்",
        "mental_support": "8. உணர்ச்சி மற்றும் மனநல ஆதரவு",
        "med_intro": "- பொதுவான மருந்துகள் (மருத்துவர் வழிகாட்டலுடன்):",
        "categories_line": "- வகைகள்: கிளினிக்கல் மதிப்பீடு, மருத்துவர் வழிகாட்டும் மருந்துகள், கண்காணிப்பு, தேவையானால் நிபுணர் பரிந்துரை.",
        "emotional_extra": "- பயம்/மனஅழுத்தம்/மனச்சோர்வு நீடித்தால் தகுதி வாய்ந்த மருத்துவர்/ஆலோசகரை அணுகவும்.",
        "method_line": "முறை: இடம்/அஞ்சல் குறியீடு → அகலம்/நெடுகு → Haversine தூரம் → அருகாமை வரிசைப்படுத்தல்.",
        "top_hospitals": "அருகிலுள்ள 5 மருத்துவமனைகள்:",
        "emergency_note": "அவசர குறிப்பு: ஆபத்தான அறிகுறிகள் கண்டறியப்பட்டன. உடனே அருகிலுள்ள அவசர வசதி கொண்ட மருத்துவமனைக்கு செல்லவும்.",
        "detected_age_group": "- கண்டறியப்பட்ட வயது குழு:",
        "contact_na": "கிடைக்கவில்லை",
        "hospital_unavailable": "மருத்துவமனை தேடல் தற்காலிகமாக கிடைக்கவில்லை. தயவு செய்து 108 ஐ அழைக்கவும் அல்லது அருகிலுள்ள PHC/அரசு மருத்துவமனைக்கு உடனே செல்லவும்.",
        "hospital_name": "மருத்துவமனை பெயர்",
        "hospital_type": "வகை",
        "hospital_specialty": "சிறப்பு",
        "hospital_address": "முழு முகவரி",
        "hospital_pincode": "அஞ்சல் குறியீடு",
        "hospital_distance": "தூரம் (கிமீ)",
        "hospital_contact": "தொடர்பு",
        "no_hospital_name": "மருத்துவமனை பெயர் இல்லை",
        "no_hospital_address": "முகவரி தகவல் இல்லை",
        "hospital_type_government": "அரசு",
        "hospital_type_private": "தனியார்",
        "specialty_general": "பொது",
        "age_child_impact": "குழந்தைகளில் {condition_name} உடல் சக்தி குறைவால் வேகமாக மோசமடையலாம்; உடனடி குழந்தை மருத்துவர் பரிசோதனை முக்கியம்.",
        "age_teen_impact": "இளம்வயதில் {condition_name} வளர்ச்சி, படிப்பு மற்றும் மனநலத்தை பாதிக்கலாம்; வயதுக்கேற்ற ஆலோசனை உதவும்.",
        "age_elderly_impact": "மூத்தவர்களில் {condition_name} நீரிழிவு/BP/இதயம்/சிறுநீரக கோளாறுகளுடன் வேகமாக மோசமடையலாம்; நெருக்கமான கண்காணிப்பு அவசியம்.",
        "age_adult_impact": "வயதானவர்களில் {condition_name} தினசரி செயல்பாடு மற்றும் வேலை திறனை பாதிக்கலாம்; நேர்மையான கண்டறிதல் நல்ல முடிவுகளை தரும்.",
        "low_info_need_details": "{topic} குறித்து பாதுகாப்பான மற்றும் பயனுள்ள வழிகாட்டலுக்கு இன்னும் சில விவரங்கள் தேவை.",
        "low_info_share_details": "அறிகுறிகள், எத்தனை நாட்கள், வயது, முன் நோய்கள் (உதா: நீரிழிவு, கர்ப்பம், BP) பகிரவும்.",
        "low_info_describe_step": "முக்கிய அறிகுறி மற்றும் காலநிலையை தெளிவாக எழுதவும் (உதாரணம்: '{query}').",
        "low_info_age_step": "வயது, கர்ப்பநிலை, நீண்டநாள் நோய்கள், தற்போது எடுத்துக் கொண்டிருக்கும் மருந்துகள் குறிப்பிடவும்.",
        "next_step_fever": "ஒவ்வொரு 6-8 மணிநேரத்திலும் காய்ச்சல்/மூச்சு அறிகுறிகளை பதிவு செய்து போதிய நீர் எடுத்துக் கொள்ளவும்.",
        "next_step_diabetes": "சர்க்கரை/BP அளவுகளை முறையாக பார்க்கவும் மற்றும் அடுத்த மருத்துவ வருகையில் பதிவை கொண்டு செல்லவும்.",
        "next_step_pregnancy": "கர்ப்பமாக இருந்தால் ANC பரிசோதனைகளை தவறாமல் செய்யவும்; இரத்தப்போக்கு அல்லது கருவழகு அசைவு குறைந்தால் உடனடி சிகிச்சை பெறவும்.",
    },
    "te": {
        "medical_section": "వైద్య మార్గదర్శక విభాగం",
        "hospital_section": "ఆసుపత్రి కనుగొనిక విభాగం (భారతదేశం మాత్రమే)",
        "condition_overview": "1. పరిస్థితి అవలోకనం",
        "age_group_impact": "2. ఈ వయస్సు వర్గంపై ప్రభావం",
        "treatment": "3. సాధారణ చికిత్స విధానాలు (వర్గాలు మాత్రమే)",
        "medicine": "4. సాధారణంగా వాడే మందుల రకాలు (డోస్ లేదు)",
        "lifestyle": "5. జీవనశైలి సూచనలు",
        "avoid": "6. దూరంగా ఉండాల్సినవి",
        "warnings": "7. అత్యవసర చికిత్స అవసరమైన హెచ్చరిక లక్షణాలు",
        "mental_support": "8. భావోద్వేగ మరియు మానసిక ఆరోగ్య మద్దతు",
        "med_intro": "- సాధారణంగా వాడే మందులు (డాక్టర్ పర్యవేక్షణలో):",
        "categories_line": "- వర్గాలు: క్లినికల్ పరీక్ష, వైద్యుడి సూచించిన మందులు, మానిటరింగ్, అవసరమైతే నిపుణుల రిఫరల్.",
        "emotional_extra": "- భయం/ఉద్వేగం/నిరుత్సాహం కొనసాగితే అర్హత కలిగిన వైద్యుడు/కౌన్సిలర్‌ను సంప్రదించండి.",
        "method_line": "విధానం: స్థలం/పిన్‌కోడ్ ఇన్‌పుట్ → అక్షాంశం/రేఖాంశం → Haversine దూరం → సమీప క్రమం.",
        "top_hospitals": "సమీపంలోని టాప్ 5 ఆసుపత్రులు:",
        "emergency_note": "అత్యవసర గమనిక: కీలక లక్షణాలు గుర్తించబడ్డాయి. వెంటనే సమీప అత్యవసర ఆసుపత్రికి వెళ్లండి.",
        "detected_age_group": "- గుర్తించిన వయస్సు వర్గం:",
        "contact_na": "అందుబాటులో లేదు",
        "hospital_unavailable": "ఆసుపత్రి శోధన తాత్కాలికంగా అందుబాటులో లేదు. దయచేసి 108కి కాల్ చేయండి లేదా సమీప PHC/ప్రభుత్వ ఆసుపత్రికి వెంటనే వెళ్లండి.",
        "hospital_name": "ఆసుపత్రి పేరు",
        "hospital_type": "రకం",
        "hospital_specialty": "ప్రత్యేకత",
        "hospital_address": "పూర్తి చిరునామా",
        "hospital_pincode": "పిన్‌కోడ్",
        "hospital_distance": "దూరం (కిమీ)",
        "hospital_contact": "సంప్రదింపు",
        "no_hospital_name": "ఆసుపత్రి పేరు అందుబాటులో లేదు",
        "no_hospital_address": "చిరునామా వివరాలు అందుబాటులో లేవు",
        "hospital_type_government": "ప్రభుత్వం",
        "hospital_type_private": "ప్రైవేట్",
        "specialty_general": "సాధారణం",
        "age_child_impact": "పిల్లల్లో {condition_name} శారీరక నిల్వ తక్కువగా ఉండటం వల్ల వేగంగా పెరగవచ్చు; తొందరగా శిశు వైద్యుడి పరీక్ష ముఖ్యం.",
        "age_teen_impact": "టీన్ వయస్సులో {condition_name} పెరుగుదల, చదువు, భావోద్వేగ ఆరోగ్యంపై ప్రభావం చూపవచ్చు; వయస్సుకు తగిన కౌన్సెలింగ్ ఉపయోగపడుతుంది.",
        "age_elderly_impact": "వృద్ధుల్లో {condition_name} మధుమేహం/BP/గుండె/మూత్రపిండ సమస్యలతో వేగంగా తీవ్రమవుతుంది; దగ్గర పర్యవేక్షణ అవసరం.",
        "age_adult_impact": "వయోజనుల్లో {condition_name} రోజువారీ పనితీరు మరియు ఉద్యోగ సామర్థ్యాన్ని ప్రభావితం చేయవచ్చు; సమయానికి నిర్ధారణ మంచిది.",
        "low_info_need_details": "{topic}పై సురక్షితమైన మరియు ఉపయోగకరమైన మార్గదర్శకత్వం ఇవ్వడానికి కొంచెం మరింత సమాచారం అవసరం.",
        "low_info_share_details": "లక్షణాలు, వ్యవధి, వయస్సు, తెలిసిన వ్యాధులు (ఉదా: మధుమేహం, గర్భం, BP) పంచండి.",
        "low_info_describe_step": "మీ ప్రధాన లక్షణం మరియు ఎంతకాలంగా ఉందో స్పష్టంగా చెప్పండి (ఉదాహరణ: '{query}').",
        "low_info_age_step": "వయస్సు, గర్భస్థితి, దీర్ఘకాలిక వ్యాధులు, ప్రస్తుతం వాడుతున్న మందులు చెప్పండి.",
        "next_step_fever": "ప్రతి 6-8 గంటలకు జ్వరం/శ్వాస లక్షణాలను గమనించి తగినంత ద్రవాలు తీసుకోండి.",
        "next_step_diabetes": "షుగర్/BPని క్రమం తప్పకుండా చూసి, తదుపరి వైద్య సందర్శనకు రికార్డు తీసుకెళ్లండి.",
        "next_step_pregnancy": "గర్భవతిగా ఉంటే ANC సందర్శనలు సమయానికి కొనసాగించండి; రక్తస్రావం లేదా భ్రూణ కదలిక తగ్గితే వెంటనే వైద్య సహాయం పొందండి.",
    },
    "bn": {
        "medical_section": "চিকিৎসা নির্দেশনা বিভাগ",
        "hospital_section": "হাসপাতাল সন্ধান বিভাগ (শুধুমাত্র ভারত)",
        "condition_overview": "1. রোগের সারাংশ",
        "age_group_impact": "2. এই বয়সে প্রভাব",
        "treatment": "3. সাধারণ চিকিৎসা পদ্ধতি (শুধু ক্যাটাগরি)",
        "medicine": "4. প্রচলিত ওষুধের ধরন (ডোজ নয়)",
        "lifestyle": "5. জীবনযাপন পরামর্শ",
        "avoid": "6. যা এড়িয়ে চলবেন",
        "warnings": "7. জরুরি চিকিৎসার সতর্ক সংকেত",
        "mental_support": "8. মানসিক ও আবেগগত সহায়তা",
        "med_intro": "- সাধারণত ব্যবহৃত ওষুধ (ডাক্তারের পরামর্শে):",
        "categories_line": "- ক্যাটাগরি: ক্লিনিক্যাল মূল্যায়ন, চিকিৎসক-নির্দেশিত ওষুধ, মনিটরিং, প্রয়োজন হলে বিশেষজ্ঞ রেফারাল।",
        "emotional_extra": "- ভয়/চাপ/হতাশা দীর্ঘস্থায়ী হলে যোগ্য ডাক্তার/কাউন্সেলরের সাথে কথা বলুন।",
        "method_line": "পদ্ধতি: লোকেশন/পিনকোড → অক্ষাংশ/দ্রাঘিমাংশ → Haversine দূরত্ব → নিকটতম ক্রমে সাজানো।",
        "top_hospitals": "নিকটতম শীর্ষ ৫ হাসপাতাল:",
        "emergency_note": "জরুরি নোট: গুরুতর উপসর্গ ধরা পড়েছে। দ্রুত নিকটতম জরুরি হাসপাতাল যান।",
        "detected_age_group": "- সনাক্তকৃত বয়স গ্রুপ:",
        "contact_na": "উপলব্ধ নয়",
        "hospital_unavailable": "হাসপাতাল অনুসন্ধান সাময়িকভাবে পাওয়া যাচ্ছে না। অনুগ্রহ করে ১০৮-এ ফোন করুন বা দ্রুত নিকটস্থ PHC/সরকারি হাসপাতালে যান।",
        "hospital_name": "হাসপাতালের নাম",
        "hospital_type": "ধরন",
        "hospital_specialty": "বিশেষত্ব",
        "hospital_address": "পূর্ণ ঠিকানা",
        "hospital_pincode": "পিনকোড",
        "hospital_distance": "দূরত্ব (কিমি)",
        "hospital_contact": "যোগাযোগ",
        "no_hospital_name": "হাসপাতালের নাম পাওয়া যায়নি",
        "no_hospital_address": "ঠিকানার বিবরণ পাওয়া যায়নি",
        "hospital_type_government": "সরকারি",
        "hospital_type_private": "বেসরকারি",
        "specialty_general": "সাধারণ",
        "age_child_impact": "শিশুদের ক্ষেত্রে {condition_name} শারীরিক রিজার্ভ কম থাকায় দ্রুত খারাপ হতে পারে; দ্রুত শিশু বিশেষজ্ঞ দেখানো জরুরি।",
        "age_teen_impact": "কিশোরদের ক্ষেত্রে {condition_name} বৃদ্ধি, পড়াশোনা ও মানসিক সুস্থতায় প্রভাব ফেলতে পারে; বয়সভিত্তিক কাউন্সেলিং সহায়ক।",
        "age_elderly_impact": "বয়স্কদের ক্ষেত্রে {condition_name} ডায়াবেটিস/BP/হৃদরোগ/কিডনি সমস্যার সাথে দ্রুত খারাপ হতে পারে; ঘন পর্যবেক্ষণ দরকার।",
        "age_adult_impact": "প্রাপ্তবয়স্কদের ক্ষেত্রে {condition_name} দৈনন্দিন কাজ ও কর্মক্ষমতায় প্রভাব ফেলতে পারে; সময়মতো নির্ণয় ফল ভালো করে।",
        "low_info_need_details": "{topic} বিষয়ে নিরাপদ ও কার্যকর নির্দেশনার জন্য আরও কিছু তথ্য দরকার।",
        "low_info_share_details": "উপসর্গ, সময়কাল, বয়স ও জানা রোগ (যেমন ডায়াবেটিস, গর্ভাবস্থা, BP) জানান।",
        "low_info_describe_step": "প্রধান উপসর্গ ও কতদিন ধরে আছে পরিষ্কারভাবে লিখুন (উদাহরণ: '{query}').",
        "low_info_age_step": "বয়স, গর্ভাবস্থা, দীর্ঘমেয়াদি রোগ ও চলমান ওষুধের তথ্য দিন।",
        "next_step_fever": "প্রতি ৬-৮ ঘণ্টায় জ্বর/শ্বাসের উপসর্গ নোট করুন এবং পর্যাপ্ত পানি পান করুন।",
        "next_step_diabetes": "শর্করা/BP নিয়মিত মাপুন এবং পরের ভিজিটে রেকর্ড সঙ্গে নিন।",
        "next_step_pregnancy": "গর্ভবতী হলে ANC ভিজিট ঠিকমতো করুন; রক্তক্ষরণ বা ভ্রূণের নড়াচড়া কমলে জরুরি চিকিৎসা নিন।",
    },
}


class HealthAssistant:
    def __init__(
        self,
        retriever: KnowledgeRetriever,
        scheme_service: SchemeService,
        disease_service: DiseaseService,
        pregnancy_service: PregnancyService,
        hospital_service: HospitalLocator | None = None,
    ):
        self.retriever = retriever
        self.scheme_service = scheme_service
        self.disease_service = disease_service
        self.pregnancy_service = pregnancy_service
        self.hospital_service = hospital_service

    @staticmethod
    def _label(language: str, key: str) -> str:
        table = SECTION_TEXT.get(language, SECTION_TEXT["en"])
        return table.get(key, SECTION_TEXT["en"][key])

    def answer(
        self,
        query: str,
        language: str,
        location: str | None = None,
        age_years: int | None = None,
    ) -> ChatResponse:
        triage_result = assess_triage(query=query, language=language)
        disclaimer = t(language, "disclaimer")
        age_group = self._derive_age_group(query=query, age_years=age_years)
        hospital_section = self._build_hospital_section(
            query=query,
            location=location,
            emergency=triage_result.is_critical,
            language=language,
        )

        if triage_result.is_critical:
            answer = self._format_medical_guidance(
                condition_name="Emergency symptoms detected",
                language=language,
                age_group=age_group,
                overview=t(language, "critical_body"),
                treatment_summary="Immediate emergency triage and hospital stabilization are required.",
                medicine_guidance=[
                    "Emergency medicines should be given only by trained clinicians.",
                    "Do not self-administer high-risk medicines or injections at home.",
                ],
                lifestyle_steps=triage_result.next_steps,
                avoid_items=[
                    "Do not delay emergency transfer.",
                    "Do not wait for symptoms to settle on their own.",
                ],
                red_flags=triage_result.matched_keywords or ["Severe chest pain", "Unconsciousness", "Severe bleeding"],
                emotional_support="Stay calm, keep the patient accompanied, and use clear communication with emergency staff.",
            )
            if hospital_section:
                answer = f"{answer}\n\n{hospital_section}"

            return ChatResponse(
                answer=answer,
                language=language,
                urgency="critical",
                disclaimer=disclaimer,
                next_steps=triage_result.next_steps,
                confidence=0.99,
                sources=[
                    SourceItem(
                        title="Emergency Triage Guidance",
                        source="MoHFW Emergency Protocol",
                        score=1.0,
                    )
                ],
            )

        scheme_intent = self.scheme_service.has_scheme_intent(query)

        if not scheme_intent and self.pregnancy_service.has_pregnancy_context(query):
            pregnancy_answer, next_steps, confidence, source = self.pregnancy_service.build_guidance(query)
            answer = self._format_medical_guidance(
                condition_name="Pregnancy support",
                language=language,
                age_group=age_group,
                overview=pregnancy_answer,
                treatment_summary="Antenatal care, blood pressure monitoring, fetal monitoring, and obstetric review are the core approaches.",
                medicine_guidance=[
                    "Pregnancy-safe medicines should be chosen only by a qualified doctor.",
                    "Iron, folic acid, calcium, and vaccines should follow ANC protocol and doctor advice.",
                    "Avoid over-the-counter painkillers, herbal medicines, or antibiotics without prescription.",
                ],
                lifestyle_steps=next_steps,
                avoid_items=[
                    "Do not skip scheduled ANC/PNC checkups.",
                    "Do not self-medicate during pregnancy.",
                ],
                red_flags=[
                    "Vaginal bleeding",
                    "Severe headache or blurred vision",
                    "Reduced fetal movement",
                    "Convulsions or severe breathlessness",
                ],
                emotional_support="Seek family support, discuss concerns with ANM/doctor, and ask for counselling if anxiety is high.",
            )
            if hospital_section:
                answer = f"{answer}\n\n{hospital_section}"

            return ChatResponse(
                answer=answer,
                language=language,
                urgency="normal",
                disclaimer=f"{disclaimer} Pregnancy symptoms should be clinically reviewed; do not self-medicate.",
                next_steps=next_steps,
                confidence=confidence,
                sources=[SourceItem(title="Pregnancy ANC Guidance", source=source, score=confidence)],
            )

        if scheme_intent:
            scheme_matches = self.scheme_service.search(query=query, language=language)
            if scheme_matches:
                scheme_answer, next_steps, source_payload = self.scheme_service.format_response(
                    matches=scheme_matches,
                    language=language,
                )
                return ChatResponse(
                    answer=scheme_answer,
                    language=language,
                    urgency="normal",
                    disclaimer=disclaimer,
                    next_steps=next_steps,
                    confidence=0.88,
                    sources=[SourceItem(**item) for item in source_payload],
                )

        disease_matches = self.disease_service.search(query=query, limit=5)
        if disease_matches:
            top_disease, disease_score = disease_matches[0]
            for candidate, candidate_score in disease_matches:
                if not self.disease_service.is_contextual_or_admin(candidate):
                    top_disease, disease_score = candidate, candidate_score
                    break

            high_quality = self.disease_service.is_high_quality_match(top_disease, disease_score, query)
            explicit_disease_query = self.disease_service.query_mentions_disease(query, top_disease)
            disease_lookup_intent = self.disease_service.has_medical_lookup_intent(query)

            if high_quality and (explicit_disease_query or disease_lookup_intent):
                answer = self._format_medical_guidance(
                    condition_name=top_disease.name,
                    language=language,
                    age_group=age_group,
                    overview=top_disease.overview,
                    treatment_summary=top_disease.treatment_summary,
                    medicine_guidance=top_disease.medicine_guidance,
                    lifestyle_steps=top_disease.home_care,
                    avoid_items=[
                        "Do not start or stop prescription medicines without medical advice.",
                        "Do not use leftover antibiotics or steroid combinations without diagnosis.",
                    ],
                    red_flags=top_disease.red_flags,
                    emotional_support="Chronic symptoms can be stressful—consider counselling/support groups and involve family in care planning.",
                )
                if hospital_section:
                    answer = f"{answer}\n\n{hospital_section}"

                return ChatResponse(
                    answer=answer,
                    language=language,
                    urgency="normal",
                    disclaimer=f"{disclaimer} Never start/stop prescription medicines without a licensed doctor.",
                    next_steps=self._build_next_steps(query=query, language=language),
                    confidence=round(min(max(disease_score, 0.55), 0.99), 2),
                    sources=[
                        SourceItem(
                            title=top_disease.name,
                            source=top_disease.source,
                            score=round(disease_score, 2),
                        )
                    ],
                )

        search_results = self.retriever.search(query=query, language=language)
        if not search_results or search_results[0][1] < 0.16:
            return self._build_low_information_response(
                query=query,
                language=language,
                disclaimer=disclaimer,
                location=location,
            )

        answer_text = self._compose_grounded_answer(search_results=search_results, language=language, query=query)
        if hospital_section:
            answer_text = f"{answer_text}\n\n{hospital_section}"
        confidence = min(max(search_results[0][1], 0.35), 0.9)

        return ChatResponse(
            answer=answer_text,
            language=language,
            urgency="normal",
            disclaimer=disclaimer,
            next_steps=self._build_next_steps(query=query, language=language),
            confidence=round(confidence, 2),
            sources=[
                SourceItem(title=item.title, source=item.source, score=round(score, 2))
                for item, score in search_results[:3]
            ],
        )

    @staticmethod
    def _extract_summary(document: KnowledgeDocument) -> str:
        sentence_end = document.content.find(".")
        if sentence_end == -1:
            return document.content[:220]
        return document.content[: sentence_end + 1]

    @staticmethod
    def _topic_from_query(query: str) -> str:
        tokens = re.findall(r"[a-zA-Z0-9]+", query.lower())
        filtered = [token for token in tokens if token not in RESPONSE_STOPWORDS and len(token) > 2]
        if not filtered:
            return "your health concern"
        return " ".join(filtered[:4])

    def _compose_grounded_answer(
        self,
        search_results: list[tuple[KnowledgeDocument, float]],
        language: str,
        query: str,
    ) -> str:
        topic = self._topic_from_query(query)
        lines = [f"{t(language, 'grounded_intro')} Topic: {topic}."]
        for document, _ in search_results[:3]:
            lines.append(f"- {document.title}: {self._extract_summary(document)}")
        return "\n".join(lines)

    def _build_next_steps(self, query: str, language: str) -> list[str]:
        lowered_query = query.lower()
        steps = [t(language, "follow_up")]

        if any(token in lowered_query for token in ["fever", "temperature", "cough", "cold", "sore throat"]):
            steps.append(self._label(language, "next_step_fever"))

        if any(token in lowered_query for token in ["sugar", "diabetes", "bp", "pressure", "hypertension"]):
            steps.append(self._label(language, "next_step_diabetes"))

        if any(token in lowered_query for token in ["pregnan", "fetal", "trimester", "weeks"]):
            steps.append(self._label(language, "next_step_pregnancy"))

        deduped: list[str] = []
        for step in steps:
            if step not in deduped:
                deduped.append(step)

        return deduped[:3]

    def _build_low_information_response(
        self,
        query: str,
        language: str,
        disclaimer: str,
        location: str | None,
    ) -> ChatResponse:
        topic = self._topic_from_query(query)
        answer = (
            f"{self._label(language, 'low_info_need_details').format(topic=topic)} "
            f"{self._label(language, 'low_info_share_details')}"
        )

        hospital_section = self._build_hospital_section(
            query=query,
            location=location,
            emergency=False,
            language=language,
        )
        if hospital_section:
            answer = f"{answer}\n\n{hospital_section}"

        next_steps = [
            self._label(language, "low_info_describe_step").format(query=query[:80]),
            self._label(language, "low_info_age_step"),
            t(language, "no_info_step_2"),
        ]

        return ChatResponse(
            answer=answer,
            language=language,
            urgency="normal",
            disclaimer=disclaimer,
            next_steps=next_steps,
            confidence=0.22,
            sources=[],
        )

    @staticmethod
    def _derive_age_group(query: str, age_years: int | None = None) -> str:
        if age_years is not None:
            if age_years <= 12:
                return "Child (0–12)"
            if age_years <= 18:
                return "Teen (13–18)"
            if age_years <= 59:
                return "Adult (19–59)"
            return "Elderly (60+)"

        lowered = query.lower()
        age_match = AGE_PATTERN.search(query)
        if age_match:
            age = int(age_match.group(1))
            if age <= 12:
                return "Child (0–12)"
            if age <= 18:
                return "Teen (13–18)"
            if age <= 59:
                return "Adult (19–59)"
            return "Elderly (60+)"

        if any(token in lowered for token in ["newborn", "infant", "child", "kid"]):
            return "Child (0–12)"
        if any(token in lowered for token in ["teen", "adolescent"]):
            return "Teen (13–18)"
        if any(token in lowered for token in ["elderly", "senior", "aged"]):
            return "Elderly (60+)"
        return "Adult (19–59)"

    @staticmethod
    def _age_group_impact(condition_name: str, age_group: str, language: str) -> str:
        table = SECTION_TEXT.get(language, SECTION_TEXT["en"])
        if age_group.startswith("Child"):
            return table["age_child_impact"].format(condition_name=condition_name)
        if age_group.startswith("Teen"):
            return table["age_teen_impact"].format(condition_name=condition_name)
        if age_group.startswith("Elderly"):
            return table["age_elderly_impact"].format(condition_name=condition_name)
        return table["age_adult_impact"].format(condition_name=condition_name)

    @staticmethod
    def _format_list(items: list[str], default_item: str) -> list[str]:
        cleaned = [item.strip() for item in items if item and item.strip()]
        return cleaned if cleaned else [default_item]

    def _format_medical_guidance(
        self,
        *,
        condition_name: str,
        language: str,
        age_group: str,
        overview: str,
        treatment_summary: str,
        medicine_guidance: list[str],
        lifestyle_steps: list[str],
        avoid_items: list[str],
        red_flags: list[str],
        emotional_support: str,
    ) -> str:
        medicines = self._format_list(medicine_guidance[:5], "Doctor-guided medicine choice after confirmed diagnosis.")
        lifestyle = self._format_list(lifestyle_steps[:5], "Maintain hydration, rest, and follow-up with a licensed doctor.")
        avoid_list = self._format_list(avoid_items[:4], "Avoid self-medication or delaying medical consultation.")
        emergency_flags = self._format_list(red_flags[:5], "Severe breathing difficulty or altered consciousness.")

        lines = [
            "------------------------------------------------------",
            "",
            self._label(language, "medical_section"),
            "",
            self._label(language, "condition_overview"),
            f"- {condition_name}: {overview}",
            "",
            self._label(language, "age_group_impact"),
            f"{self._label(language, 'detected_age_group')} {age_group}",
            f"- {self._age_group_impact(condition_name, age_group, language)}",
            "",
            self._label(language, "treatment"),
            f"- {treatment_summary}",
            self._label(language, "categories_line"),
            "",
            self._label(language, "medicine"),
            self._label(language, "med_intro"),
        ]
        lines.extend([f"  - {item}" for item in medicines])
        lines.extend(
            [
                "",
                self._label(language, "lifestyle"),
            ]
        )
        lines.extend([f"- {item}" for item in lifestyle])
        lines.extend(
            [
                "",
                self._label(language, "avoid"),
            ]
        )
        lines.extend([f"- {item}" for item in avoid_list])
        lines.extend(
            [
                "",
                self._label(language, "warnings"),
            ]
        )
        lines.extend([f"- {item}" for item in emergency_flags])
        lines.extend(
            [
                "",
                self._label(language, "mental_support"),
                f"- {emotional_support}",
                self._label(language, "emotional_extra"),
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _extract_pincode(value: str | None) -> str | None:
        if not value:
            return None
        match = PINCODE_PATTERN.search(value)
        return match.group(0) if match else None

    def _infer_hospital_type(self, name: str, language: str) -> str:
        lowered = name.lower()
        if any(marker in lowered for marker in GOVERNMENT_HOSPITAL_MARKERS):
            return self._label(language, "hospital_type_government")
        return self._label(language, "hospital_type_private")

    def _infer_specialty(self, name: str, language: str) -> str:
        lowered = name.lower()
        for keyword, specialty in SPECIALTY_HINTS.items():
            if keyword in lowered:
                return specialty
        return self._label(language, "specialty_general")

    def _build_hospital_section(self, query: str, location: str | None, emergency: bool, language: str) -> str:
        if not self.hospital_service:
            return ""

        pincode = self._extract_pincode(query) or self._extract_pincode(location)
        hospital_payload = None
        try:
            if pincode:
                hospital_payload = self.hospital_service.lookup_nearest(pincode=pincode, limit=5)
            elif location and location.strip():
                hospital_payload = self.hospital_service.lookup_nearest_by_location(location=location.strip(), limit=5)
        except HospitalLookupError:
            return (
                "------------------------------------------------------\n\n"
                f"{self._label(language, 'hospital_section')}\n\n"
                f"{self._label(language, 'hospital_unavailable')}"
            )

        if not hospital_payload:
            return ""

        hospitals = hospital_payload.get("hospitals", [])[:5]
        if not hospitals:
            return ""

        lines = [
            "------------------------------------------------------",
            "",
            self._label(language, "hospital_section"),
            "",
            self._label(language, "method_line"),
        ]
        if emergency:
            lines.append(self._label(language, "emergency_note"))

        lines.append("")
        lines.append(self._label(language, "top_hospitals"))

        for index, hospital in enumerate(hospitals, start=1):
            name = hospital.get("name", self._label(language, "no_hospital_name"))
            address = hospital.get("address", self._label(language, "no_hospital_address"))
            hospital_type = self._infer_hospital_type(name, language)
            specialty = self._infer_specialty(name, language)
            distance = hospital.get("distance_km", "NA")
            hospital_pincode = (
                self._extract_pincode(address)
                or hospital_payload.get("pincode")
                or self._label(language, "contact_na")
            )
            contact = hospital.get("contact") or self._label(language, "contact_na")

            lines.extend(
                [
                    f"{index}. {self._label(language, 'hospital_name')}: {name}",
                    f"   - {self._label(language, 'hospital_type')}: {hospital_type}",
                    f"   - {self._label(language, 'hospital_specialty')}: {specialty}",
                    f"   - {self._label(language, 'hospital_address')}: {address}",
                    f"   - {self._label(language, 'hospital_pincode')}: {hospital_pincode}",
                    f"   - {self._label(language, 'hospital_distance')}: {distance}",
                    f"   - {self._label(language, 'hospital_contact')}: {contact}",
                ]
            )

        return "\n".join(lines)
