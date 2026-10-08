"""Create test resume and JD PDFs for testing the weightage analysis."""
import fitz  # pymupdf

def text_to_pdf(text: str, output_path: str, title: str):
    """Write text to a multi-page PDF that fits all content."""
    doc = fitz.open()
    lines = text.strip().split("\n")
    
    fontsize = 10
    margin = 50
    line_height = fontsize * 1.4
    page_width = 595  # A4
    page_height = 842  # A4
    usable_height = page_height - 2 * margin
    lines_per_page = int(usable_height / line_height)
    
    page = None
    y = margin
    
    for i, line in enumerate(lines):
        if page is None or y > page_height - margin:
            page = doc.new_page(width=page_width, height=page_height)
            y = margin
        
        page.insert_text((margin, y), line, fontsize=fontsize, fontname="helv")
        y += line_height
    
    doc.save(output_path)
    pages = len(doc)
    doc.close()
    print(f"Created: {output_path} ({pages} pages)")


# Resume
resume_text = """VENKAT SAI ANIL KUMAR
AI Engineer | 4 Years Experience
Email: venkatsai@email.com | Phone: +91 9966933336 | Hyderabad, India

SUMMARY

AI/ML Engineer with 4 years of experience building and deploying machine learning
models. Strong in Python, NLP, and cloud-based ML workflows. Experience with LLMs
and RAG pipelines. Looking for senior AI engineer roles to deepen expertise in
agentic AI and production ML systems.

EXPERIENCE

AI Engineer - Minfy Technologies (2022 - Present)
- Built RAG pipelines using LangChain, ChromaDB, and Amazon Bedrock
  for enterprise document Q&A systems
- Developed and deployed ML models on Amazon SageMaker for customer
  churn prediction (AUC 0.89) and lead scoring
- Implemented prompt engineering strategies for Gemini and Claude models,
  improving response accuracy by 35%
- Built automated document ingestion pipeline processing 10K+ PDFs/day
  with chunking, embedding generation, and vector storage
- Created LLM evaluation framework measuring hallucination rates,
  relevance scores, and grounding quality
- Worked with cross-functional teams to translate business requirements
  into ML solutions

ML Engineer - Wipro (2021 - 2022)
- Trained and deployed classification models using scikit-learn and
  TensorFlow for insurance claim fraud detection
- Built feature engineering pipelines for structured and unstructured data
- Implemented model versioning using MLflow and experiment tracking
- Deployed models using Docker containers on AWS ECS
- Collaborated with data engineering team on ETL pipelines (AWS Glue, Redshift)

Data Science Intern - Infosys (2020 - 2021)
- Built sentiment analysis models using BERT and spaCy
- Created dashboards using Python, Pandas, and Matplotlib
- Assisted senior data scientists with model evaluation

EDUCATION

M.Tech Artificial Intelligence - IIIT Hyderabad (2018 - 2020)
- Thesis: Attention mechanisms for low-resource language translation
- CGPA: 8.7/10

B.Tech Computer Science - JNTU Hyderabad (2014 - 2018)
- CGPA: 7.9/10

TECHNICAL SKILLS

Languages: Python (expert), SQL, JavaScript (basic)
ML/DL: scikit-learn, TensorFlow, PyTorch, HuggingFace Transformers
LLM/GenAI: LangChain, Amazon Bedrock, OpenAI API, ChromaDB, Pinecone
Cloud: AWS (SageMaker, S3, Lambda, Bedrock, Redshift, IAM, ECS)
MLOps: MLflow, Docker, basic Kubernetes exposure, SageMaker Pipelines
Tools: Git, Jupyter, FastAPI, Streamlit, Grafana
Data: Pandas, NumPy, Spark (basic), PostgreSQL

CERTIFICATIONS

- AWS Certified Machine Learning Specialty (2023)
- AWS Solutions Architect Associate (2022)
- DeepLearning.AI LLM Specialization (2024)

PROJECTS

- Enterprise Knowledge Bot: RAG system serving 500+ internal users,
  using Bedrock Claude + Pinecone, 92% answer accuracy
- Automated Resume Screener: ML pipeline scoring 1000+ resumes/day
  against JD requirements using embeddings and semantic similarity
- Real-time Anomaly Detection: Streaming anomaly detection on IoT
  sensor data using SageMaker and Kinesis
"""

# JD
jd_text = """AI ENGINEER
Experience: 6 Years | Location: Gurugram | Type: Full-Time

EDUCATION

Bachelor's or Master's degree in Computer Science, Data Science, Statistics,
Mathematics, or a related field.
Strong academic foundation in statistics, probability, and machine learning.

CORE EXPERIENCE

- 5-8 years of professional experience in Data Science, ML, or Applied AI
- Hands-on experience building, training, and deploying ML models in production
- Strong understanding of data preprocessing, feature engineering, model evaluation
- Experience working on end-to-end ML workflows
- Ability to translate business and product requirements into data-driven solutions

MACHINE LEARNING AND MLOPS

Practical experience using Amazon SageMaker for:
- Model training and tuning
- Model deployment and inference

Experience with common ML algorithms using scikit-learn, TensorFlow, or PyTorch

Familiarity with MLOps concepts such as:
- Model versioning
- Experiment tracking
- Basic monitoring and retraining workflows

Working knowledge of Docker and exposure to Kubernetes-based deployments
Experience collaborating with ML engineers to operationalize models

GENERATIVE AI AND LLMS

- Hands-on experience developing LLM-powered applications using Amazon Bedrock
  or similar platforms
- Experience building or contributing to RAG pipelines, including:
  - Document ingestion and chunking
  - Embedding generation
  - Similarity search using vector databases
- Practical knowledge of prompt engineering, prompt tuning, and output evaluation
- Understanding of LLM failure modes (hallucinations, grounding issues)
- Ability to evaluate LLM responses for accuracy, relevance, and safety

AGENTIC AI (GROWING EXPERTISE)

- Exposure to Agentic AI concepts and frameworks such as AgentCore
- Experience implementing:
  - Simple Autonomous agents or workflows
  - Multi-step reasoning with predefined tools
- Familiarity with tool-calling, agent orchestration, and workflow automation
- Understanding the importance of:
  - Guardrails
  - Human-in-the-loop mechanisms
  - Logging and observability for agent behavior

CLOUD PLATFORM

Working knowledge of key AWS services, including:
- S3, Lambda, Redshift, IAM

PROFESSIONAL AND COLLABORATION SKILLS

- Strong Python programming skills and experience working with APIs
- Ability to work effectively in cross-functional teams
- Willingness to learn quickly in a fast-evolving AI landscape
- Clear communication of findings and model behavior to non-technical stakeholders

NICE TO HAVE

- Exposure to AI governance, compliance, or ethical AI practices
- Experience with monitoring LLM outputs and evaluation frameworks
- Certifications in AWS, Machine Learning, or Data Science
- Prior experience in enterprise or cloud-native environments

REQUIRED SKILLS

- Artificial Intelligence / Machine Learning
- Agentic AI
"""

text_to_pdf(resume_text, "test_data/sample_resume.pdf", "Resume")
text_to_pdf(jd_text, "test_data/sample_jd.pdf", "Job Description")
