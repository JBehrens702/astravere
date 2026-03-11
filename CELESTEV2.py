import streamlit as st

# FellianSynchophite to Celestial events

def get_solstices(dayAci):
    year = dayAci // 360
    month = (dayAci % 360) // 30
    day = (dayAci % 360) % 30 + 1

    output = []
    output.append(f"RESULTS FOR: {day}/{month}/{year}")

    if dayAci % 160160 == 0:
        output.append("PERFECT SOLSTICE")
        output.append("Zanacleus Prison Plane OPEN")
        output.append("Oenoria Prison Plane OPEN")

    if dayAci % 40040 == 0:
        output.append("Celestial Plane OPEN")
        output.append("Epinium Prison Plane OPEN")

    if dayAci % 2288 == 0:
        output.append("Beastland Plane OPEN")

    if dayAci % 416 == 0:
        output.append("Plane of Air OPEN")

    if dayAci % 364 == 0:
        output.append("Plane of Nature OPEN")

    if dayAci % 160 == 0:
        output.append("Storm Plane OPEN")

    if dayAci % 104 == 0:
        output.append("Fire Plane OPEN")

    if dayAci % 77 == 0:
        output.append("Water Plane OPEN")

    if dayAci % 40 == 0:
        output.append("Earth Plane OPEN")

    if dayAci % 10 == 0:
        output.append("Plane of Light OPEN")

    output.append("Asterium may be accessible")
    output.append("Hells may be accessible")
    output.append("Status of FEYWILD PORTAL unknown")

    return output


# -------------------------
# Streamlit App Starts Here
# -------------------------

st.title("Fellian Synchophite Celestial Events")

# Store dayAci in session state
if "dayAci" not in st.session_state:
    st.session_state.dayAci = None

date_input = st.text_input("Enter the date (DD/MM/YYYY):")

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Check Date"):
        try:
            day, month, year = map(int, date_input.split('/'))
            st.session_state.dayAci = ((day - 1) + ((month * 30) - 1) + ((year * 360) - 1))
        except:
            st.error("Invalid date format. Use DD/MM/YYYY")

with col2:
    if st.button("Next Day"):
        if st.session_state.dayAci is not None:
            st.session_state.dayAci += 1

with col3:
    if st.button("Prev Day"):
        if st.session_state.dayAci is not None:
            st.session_state.dayAci -= 1

# Display results
if st.session_state.dayAci is not None:
    results = get_solstices(st.session_state.dayAci)

    st.divider()
    for line in results:
        st.write(line)