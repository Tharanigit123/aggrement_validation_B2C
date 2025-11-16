
import streamlit as st, tempfile, json, os
from validator import AgreementValidator

st.set_page_config(page_title="Agreement Validation — B2C", layout="wide")
st.title("Agreement Validation — B2C")

col1,col2=st.columns(2)
with col1:
    main=st.file_uploader("Main Agreement (PDF)",type=["pdf"])
with col2:
    client=st.file_uploader("Client Agreement (PDF)",type=["pdf"])

st.markdown("### Additional Documents (optional)")
docs=st.file_uploader("Upload multiple PDFs",type=["pdf"],accept_multiple_files=True)

if st.button("Run Validation"):
    if not main or not client:
        st.error("Upload both Main & Client PDFs.")
    else:
        with tempfile.NamedTemporaryFile(delete=False,suffix=".pdf") as f:
            f.write(main.read()); main_p=f.name
        with tempfile.NamedTemporaryFile(delete=False,suffix=".pdf") as f:
            f.write(client.read()); client_p=f.name

        doc_paths=[]; doc_names=[]
        if docs:
            for d in docs:
                with tempfile.NamedTemporaryFile(delete=False,suffix=".pdf") as f:
                    f.write(d.read()); doc_paths.append(f.name); doc_names.append(d.name)

        val=AgreementValidator()
        with st.spinner("Validating..."):
            out=val.validate(main_p,client_p,documents=doc_paths,document_names=doc_names)

        st.success("Done")

        st.subheader("PAN/GST")
        st.write(out["pan"]); st.write(out["gst"])

        st.subheader("COI / Rate Keywords")
        st.write(out["coi_keywords"]); st.write(out["rate_keywords"])

        st.subheader("Diff")
        st.write(out["diff"])

        st.subheader("Clause Similarity")
        st.write(out["clause_similarity_samples"][:10])

        st.subheader("Documents")
        st.write(out["documents"])

        st.download_button("Download JSON",json.dumps(out,indent=2),"validation.json")
