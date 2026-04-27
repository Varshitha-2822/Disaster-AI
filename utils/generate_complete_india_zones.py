"""
Generate Complete India Zones Data
Covers all 28 states, 8 union territories, and all major districts
"""

from datetime import datetime
import json

# Complete list of all Indian states and union territories with their districts
INDIA_COMPLETE_STRUCTURE = {
    # Union Territories
    "Delhi": {
        "districts": ["Central Delhi", "North Delhi", "South Delhi", "East Delhi", "West Delhi", 
                     "North East Delhi", "North West Delhi", "South West Delhi", "New Delhi", "Shahdara"],
        "coords_base": [28.6, 77.1],
        "risk_base": 0.50
    },
    "Jammu and Kashmir": {
        "districts": ["Jammu", "Srinagar", "Anantnag", "Baramulla", "Udhampur", "Kathua", "Pulwama", 
                     "Kupwara", "Rajouri", "Poonch", "Doda", "Kishtwar", "Ramban", "Reasi", "Samba", 
                     "Budgam", "Ganderbal", "Kulgam", "Shopian", "Bandipora"],
        "coords_base": [33.8, 74.8],
        "risk_base": 0.75
    },
    "Ladakh": {
        "districts": ["Leh", "Kargil"],
        "coords_base": [34.2, 77.5],
        "risk_base": 0.45
    },
    "Chandigarh": {
        "districts": ["Chandigarh"],
        "coords_base": [30.7, 76.8],
        "risk_base": 0.38
    },
    "Puducherry": {
        "districts": ["Puducherry", "Karaikal", "Mahe", "Yanam"],
        "coords_base": [11.9, 79.8],
        "risk_base": 0.60
    },
    "Andaman and Nicobar Islands": {
        "districts": ["Port Blair", "Car Nicobar", "Mayabunder", "Diglipur"],
        "coords_base": [11.7, 92.8],
        "risk_base": 0.55
    },
    "Lakshadweep": {
        "districts": ["Kavaratti", "Amini", "Minicoy"],
        "coords_base": [10.5, 72.6],
        "risk_base": 0.70
    },
    "Dadra and Nagar Haveli and Daman and Diu": {
        "districts": ["Daman", "Diu", "Silvassa"],
        "coords_base": [20.4, 72.9],
        "risk_base": 0.52
    },
    
    # States - Northern
    "Punjab": {
        "districts": ["Amritsar", "Ludhiana", "Patiala", "Jalandhar", "Bathinda", "Hoshiarpur", 
                     "Gurdaspur", "Ferozepur", "Sangrur", "Moga", "Muktsar", "Faridkot", "Rupnagar", 
                     "Fatehgarh Sahib", "Kapurthala", "Nawanshahr", "Tarn Taran", "Barnala", "Mohali"],
        "coords_base": [30.9, 75.8],
        "risk_base": 0.52
    },
    "Haryana": {
        "districts": ["Gurgaon", "Faridabad", "Panipat", "Karnal", "Hisar", "Rohtak", "Ambala", 
                     "Yamunanagar", "Kurukshetra", "Kaithal", "Jind", "Sonipat", "Rewari", "Bhiwani", 
                     "Sirsa", "Fatehabad", "Jhajjar", "Palwal", "Mewat", "Panchkula"],
        "coords_base": [29.0, 76.1],
        "risk_base": 0.48
    },
    "Himachal Pradesh": {
        "districts": ["Shimla", "Kangra", "Mandi", "Solan", "Kullu", "Chamba", "Una", "Hamirpur", 
                     "Bilaspur", "Sirmaur", "Kinnaur", "Lahaul and Spiti"],
        "coords_base": [31.1, 77.1],
        "risk_base": 0.70
    },
    "Uttarakhand": {
        "districts": ["Dehradun", "Haridwar", "Uttarkashi", "Chamoli", "Rudraprayag", "Tehri Garhwal", 
                     "Pauri Garhwal", "Pithoragarh", "Bageshwar", "Almora", "Champawat", "Nainital", 
                     "Udham Singh Nagar", "Hardwar"],
        "coords_base": [30.3, 78.0],
        "risk_base": 0.88
    },
    "Rajasthan": {
        "districts": ["Jaipur", "Jodhpur", "Udaipur", "Kota", "Bikaner", "Ajmer", "Bhilwara", 
                     "Alwar", "Bharatpur", "Sikar", "Jhunjhunu", "Churu", "Nagaur", "Pali", "Barmer", 
                     "Jaisalmer", "Jalore", "Sirohi", "Dungarpur", "Banswara", "Chittorgarh", 
                     "Rajsamand", "Bundi", "Tonk", "Karauli", "Dholpur", "Sawai Madhopur", "Dausa", 
                     "Hanumangarh", "Sri Ganganagar", "Baran", "Jhalawar", "Pratapgarh"],
        "coords_base": [26.9, 75.8],
        "risk_base": 0.35
    },
    
    # States - Eastern
    "West Bengal": {
        "districts": ["Kolkata", "Howrah", "North 24 Parganas", "South 24 Parganas", "Murshidabad", 
                     "Malda", "Nadia", "Bardhaman", "Birbhum", "Bankura", "Purulia", "Hooghly", 
                     "Medinipur", "Jalpaiguri", "Darjeeling", "Cooch Behar", "Alipurduar", 
                     "Kalimpong", "Paschim Medinipur", "Purba Medinipur", "Dakshin Dinajpur", 
                     "Uttar Dinajpur"],
        "coords_base": [22.6, 88.4],
        "risk_base": 0.88
    },
    "Bihar": {
        "districts": ["Patna", "Muzaffarpur", "Darbhanga", "Bhagalpur", "Purnia", "Gaya", "Arrah", 
                     "Bettiah", "Motihari", "Sitamarhi", "Saharsa", "Katihar", "Madhepura", 
                     "Kishanganj", "Araria", "Supaul", "Madhubani", "Samastipur", "Begusarai", 
                     "Munger", "Jamui", "Lakhisarai", "Sheikhpura", "Nalanda", "Bhojpur", "Buxar", 
                     "Kaimur", "Rohtas", "Aurangabad", "Gopalganj", "Siwan", "Saran", "Vaishali", 
                     "East Champaran", "West Champaran", "Sheohar", "Sitamarhi", "Muzaffarpur", 
                     "Vaishali", "Saran", "Siwan", "Gopalganj", "West Champaran", "East Champaran"],
        "coords_base": [25.6, 85.1],
        "risk_base": 0.90
    },
    "Jharkhand": {
        "districts": ["Ranchi", "Jamshedpur", "Dhanbad", "Bokaro", "Hazaribagh", "Giridih", "Deoghar", 
                     "Dumka", "Pakur", "Godda", "Sahibganj", "Palamu", "Garhwa", "Latehar", "Gumla", 
                     "Simdega", "Lohardaga", "Khunti", "West Singhbhum", "East Singhbhum", "Seraikela-Kharsawan"],
        "coords_base": [23.3, 85.3],
        "risk_base": 0.65
    },
    "Odisha": {
        "districts": ["Bhubaneswar", "Cuttack", "Puri", "Balasore", "Bhadrak", "Jajpur", "Kendrapara", 
                     "Jagatsinghpur", "Khordha", "Nayagarh", "Ganjam", "Gajapati", "Kandhamal", 
                     "Boudh", "Sambalpur", "Deogarh", "Sundargarh", "Jharsuguda", "Bargarh", 
                     "Bolangir", "Nuapada", "Kalahandi", "Rayagada", "Koraput", "Malkangiri", 
                     "Nabarangpur", "Mayurbhanj", "Keonjhar", "Dhenkanal", "Angul"],
        "coords_base": [20.3, 85.8],
        "risk_base": 0.75
    },
    "Assam": {
        "districts": ["Guwahati", "Dibrugarh", "Jorhat", "Silchar", "Tezpur", "Nagaon", "Barpeta", 
                     "Dhubri", "Goalpara", "Bongaigaon", "Kokrajhar", "Chirang", "Baksa", "Udalguri", 
                     "Darrang", "Sonitpur", "Lakhimpur", "Dhemaji", "Tinsukia", "Sivasagar", 
                     "Golaghat", "Karbi Anglong", "Dima Hasao", "Cachar", "Karimganj", "Hailakandi"],
        "coords_base": [26.2, 92.9],
        "risk_base": 0.90
    },
    "Sikkim": {
        "districts": ["Gangtok", "Namchi", "Mangan", "Geyzing"],
        "coords_base": [27.3, 88.6],
        "risk_base": 0.75
    },
    "Arunachal Pradesh": {
        "districts": ["Itanagar", "Tawang", "West Kameng", "East Kameng", "Papum Pare", "Lower Subansiri", 
                     "Upper Subansiri", "West Siang", "East Siang", "Upper Siang", "Dibang Valley", 
                     "Lohit", "Anjaw", "Changlang", "Tirap", "Longding", "Lower Dibang Valley", 
                     "Kurung Kumey", "Kra Daadi", "Namsai", "Siang", "Kamle", "Lepa Rada", "Shi Yomi"],
        "coords_base": [28.2, 94.7],
        "risk_base": 0.80
    },
    "Nagaland": {
        "districts": ["Kohima", "Dimapur", "Mokokchung", "Tuensang", "Wokha", "Zunheboto", "Phek", 
                     "Mon", "Kiphire", "Longleng", "Peren"],
        "coords_base": [25.7, 94.1],
        "risk_base": 0.78
    },
    "Manipur": {
        "districts": ["Imphal", "Thoubal", "Bishnupur", "Churachandpur", "Chandel", "Senapati", 
                     "Tamenglong", "Ukhrul", "Kangpokpi", "Kakching", "Tengnoupal", "Jiribam", 
                     "Noney", "Pherzawl", "Kamjong"],
        "coords_base": [24.8, 93.9],
        "risk_base": 0.80
    },
    "Mizoram": {
        "districts": ["Aizawl", "Lunglei", "Saiha", "Champhai", "Kolasib", "Serchhip", "Lawngtlai", 
                     "Mamit", "Hnahthial", "Saitual", "Khawzawl"],
        "coords_base": [23.7, 92.7],
        "risk_base": 0.75
    },
    "Tripura": {
        "districts": ["Agartala", "West Tripura", "South Tripura", "Dhalai", "North Tripura", 
                     "Khowai", "Sepahijala", "Unakoti", "Gomati"],
        "coords_base": [23.8, 91.3],
        "risk_base": 0.60
    },
    "Meghalaya": {
        "districts": ["Shillong", "Tura", "Jowai", "Nongpoh", "Nongstoin", "Williamnagar", "Resubelpara", 
                     "Ampati", "Baghmara", "Khliehriat", "Mairang", "Mawkyrwat"],
        "coords_base": [25.6, 91.9],
        "risk_base": 0.85
    },
    
    # States - Central
    "Madhya Pradesh": {
        "districts": ["Bhopal", "Indore", "Gwalior", "Jabalpur", "Raipur", "Bilaspur", "Durg", 
                     "Rajgarh", "Ratlam", "Ujjain", "Sagar", "Satna", "Rewa", "Chhindwara", 
                     "Betul", "Hoshangabad", "Harda", "Khandwa", "Burhanpur", "Khargone", 
                     "Barwani", "Dhar", "Jhabua", "Alirajpur", "Mandsaur", "Neemuch", "Shajapur", 
                     "Dewas", "Sehore", "Vidisha", "Raisen", "Narsinghpur", "Damoh", "Panna", 
                     "Tikamgarh", "Chhatarpur", "Shivpuri", "Guna", "Ashoknagar", "Sheopur", 
                     "Morena", "Bhind", "Datia", "Shivpuri", "Gwalior", "Ashoknagar", "Shajapur"],
        "coords_base": [23.3, 77.4],
        "risk_base": 0.58
    },
    "Chhattisgarh": {
        "districts": ["Raipur", "Bilaspur", "Durg", "Rajgarh", "Korba", "Raigarh", "Jashpur", 
                     "Surguja", "Koriya", "Balrampur", "Surajpur", "Jashpur", "Raigarh", "Korba", 
                     "Janjgir-Champa", "Mungeli", "Kabirdham", "Bemetara", "Balod", "Dhamtari", 
                     "Gariaband", "Mahasamund", "Durg", "Balod Bazar", "Bhilai", "Rajnandgaon", 
                     "Kanker", "Narayanpur", "Bastar", "Dantewada", "Bijapur", "Sukma", "Kondagaon"],
        "coords_base": [21.3, 81.6],
        "risk_base": 0.52
    },
    
    # States - Western
    "Maharashtra": {
        "districts": ["Mumbai", "Pune", "Nashik", "Nagpur", "Aurangabad", "Kolhapur", "Sangli", 
                     "Satara", "Solapur", "Ahmednagar", "Jalgaon", "Dhule", "Nandurbar", "Parbhani", 
                     "Hingoli", "Nanded", "Latur", "Osmanabad", "Beed", "Jalna", "Buldhana", 
                     "Akola", "Washim", "Amravati", "Yavatmal", "Wardha", "Chandrapur", "Gadchiroli", 
                     "Bhandara", "Gondia", "Raigad", "Thane", "Palghar", "Ratnagiri", "Sindhudurg"],
        "coords_base": [19.1, 73.8],
        "risk_base": 0.65
    },
    "Gujarat": {
        "districts": ["Ahmedabad", "Surat", "Vadodara", "Rajkot", "Bhavnagar", "Jamnagar", 
                     "Junagadh", "Gandhinagar", "Mehsana", "Palanpur", "Patan", "Surendranagar", 
                     "Morbi", "Kutch", "Banaskantha", "Sabarkantha", "Aravalli", "Dahod", "Panchmahal", 
                     "Mahisagar", "Kheda", "Anand", "Bharuch", "Narmada", "Surat", "Tapi", "Dang", 
                     "Navsari", "Valsad", "Daman", "Diu"],
        "coords_base": [23.0, 72.6],
        "risk_base": 0.50
    },
    "Goa": {
        "districts": ["North Goa", "South Goa"],
        "coords_base": [15.5, 73.8],
        "risk_base": 0.52
    },
    
    # States - Southern
    "Karnataka": {
        "districts": ["Bangalore", "Mysore", "Mangalore", "Hubli", "Belgaum", "Gulbarga", "Bijapur", 
                     "Raichur", "Bellary", "Davangere", "Shimoga", "Tumkur", "Chitradurga", 
                     "Kolar", "Mandya", "Hassan", "Chikmagalur", "Udupi", "Dakshina Kannada", 
                     "Uttara Kannada", "Dharwad", "Gadag", "Haveri", "Bagalkot", "Koppal", 
                     "Yadgir", "Bidar", "Kalaburagi", "Vijayapura", "Ballari", "Koppal", "Raichur", 
                     "Yadgir", "Chamarajanagar", "Kodagu", "Chikkaballapur", "Ramanagara"],
        "coords_base": [12.9, 77.6],
        "risk_base": 0.58
    },
    "Kerala": {
        "districts": ["Kochi", "Thiruvananthapuram", "Kozhikode", "Thrissur", "Alappuzha", "Kollam", 
                     "Kannur", "Kasaragod", "Pathanamthitta", "Idukki", "Palakkad", "Malappuram", 
                     "Wayanad", "Ernakulam"],
        "coords_base": [10.0, 76.3],
        "risk_base": 0.80
    },
    "Tamil Nadu": {
        "districts": ["Chennai", "Coimbatore", "Madurai", "Tiruchirappalli", "Salem", "Tirunelveli", 
                     "Erode", "Vellore", "Dindigul", "Thanjavur", "Tuticorin", "Kanchipuram", 
                     "Tiruvallur", "Villupuram", "Cuddalore", "Nagapattinam", "Thiruvarur", 
                     "Pudukkottai", "Sivaganga", "Ramanathapuram", "Theni", "Krishnagiri", 
                     "Dharmapuri", "Namakkal", "Karur", "Perambalur", "Ariyalur", "Nilgiris", 
                     "Coimbatore", "Tiruppur", "Karur", "Dindigul", "Theni", "Madurai", "Sivaganga", 
                     "Ramanathapuram", "Virudhunagar", "Tuticorin", "Tirunelveli", "Kanniyakumari"],
        "coords_base": [11.0, 78.2],
        "risk_base": 0.65
    },
    "Andhra Pradesh": {
        "districts": ["Hyderabad", "Visakhapatnam", "Vijayawada", "Guntur", "Nellore", "Kurnool", 
                     "Anantapur", "Chittoor", "Kadapa", "Ongole", "Eluru", "Machilipatnam", 
                     "Srikakulam", "Vizianagaram", "East Godavari", "West Godavari", "Krishna", 
                     "Guntur", "Prakasam", "Nellore", "Chittoor", "Kadapa", "Anantapur", "Kurnool"],
        "coords_base": [15.9, 79.0],
        "risk_base": 0.70
    },
    "Telangana": {
        "districts": ["Hyderabad", "Warangal", "Karimnagar", "Nizamabad", "Khammam", "Mahabubnagar", 
                     "Medak", "Nalgonda", "Adilabad", "Rangareddy", "Sangareddy", "Siddipet", 
                     "Jagitial", "Peddapalli", "Mancherial", "Komaram Bheem", "Bhadradri Kothagudem", 
                     "Mahabubabad", "Jangaon", "Yadadri Bhuvanagiri", "Suryapet", "Vikarabad", 
                     "Wanaparthy", "Narayanpet", "Jogulamba Gadwal", "Nagarkurnool", "Wanaparthy"],
        "coords_base": [18.0, 79.4],
        "risk_base": 0.58
    },
}

def generate_zone_id(state_name, district_name):
    """Generate unique zone ID from state and district"""
    state_code = state_name.replace(" ", "_").lower()[:3]
    district_code = district_name.replace(" ", "_").lower()[:10]
    return f"{state_code}_{district_code}"

def calculate_coords(base_coords, index, total):
    """Calculate coordinates for district based on base and index"""
    lat, lon = base_coords
    # Spread districts around base coordinates
    lat_offset = (index % 5 - 2) * 0.3
    lon_offset = (index // 5 - 2) * 0.3
    return [
        [lat + lat_offset, lon + lon_offset],
        [lat + lat_offset + 0.3, lon + lon_offset],
        [lat + lat_offset + 0.3, lon + lon_offset + 0.3],
        [lat + lat_offset, lon + lon_offset + 0.3]
    ]

def estimate_infrastructure(population, risk_score):
    """Estimate infrastructure based on population and risk"""
    hospitals = max(2, int(population / 50000))
    schools = max(5, int(population / 8000))
    roads_km = max(50, int(population / 2000))
    return hospitals, schools, roads_km

def generate_complete_zones():
    """Generate complete zones data for all of India"""
    zones = []
    
    for state_name, state_data in INDIA_COMPLETE_STRUCTURE.items():
        districts = state_data["districts"]
        base_coords = state_data["coords_base"]
        base_risk = state_data["risk_base"]
        
        for idx, district in enumerate(districts):
            zone_id = generate_zone_id(state_name, district)
            coords = calculate_coords(base_coords, idx, len(districts))
            
            # Vary risk slightly per district
            risk_variation = (idx % 5 - 2) * 0.05
            risk_score = max(0.2, min(0.95, base_risk + risk_variation))
            
            # Determine risk level
            if risk_score >= 0.8:
                risk_level = "SEVERE"
            elif risk_score >= 0.6:
                risk_level = "HIGH"
            elif risk_score >= 0.4:
                risk_level = "MODERATE"
            else:
                risk_level = "LOW"
            
            # Estimate population (varies by district index)
            population = 500000 + (idx * 150000) + (len(districts) * 10000)
            
            # Estimate infrastructure
            hospitals, schools, roads_km = estimate_infrastructure(population, risk_score)
            
            zone = {
                "id": zone_id,
                "name": f"{district}",
                "state": state_name,
                "coords": coords,
                "risk_level": risk_level,
                "risk_score": round(risk_score, 2),
                "hospitals": hospitals,
                "schools": schools,
                "roads_km": roads_km,
                "population": population,
                "last_update": datetime.now().isoformat()
            }
            zones.append(zone)
    
    return zones

if __name__ == "__main__":
    zones = generate_complete_zones()
    
    # Save to JSON file
    with open("data/complete_india_zones.json", "w") as f:
        json.dump(zones, f, indent=2)
    
    # Also generate Python list format
    with open("data/complete_india_zones.py", "w") as f:
        f.write("from datetime import datetime\n\n")
        f.write("COMPLETE_INDIA_ZONES = [\n")
        for zone in zones:
            f.write(f"    {repr(zone)},\n")
        f.write("]\n")
    
    print(f"Generated {len(zones)} zones covering all of India")
    print(f"   States/UTs: {len(INDIA_COMPLETE_STRUCTURE)}")
    print(f"   Total districts: {sum(len(v['districts']) for v in INDIA_COMPLETE_STRUCTURE.values())}")

