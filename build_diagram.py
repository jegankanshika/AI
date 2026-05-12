"""Generate Credit Co-Pilot architecture diagram using mingrammer/diagrams."""
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import EKS, Lambda
from diagrams.aws.storage import S3
from diagrams.aws.security import KMS, SecretsManager
from diagrams.aws.network import APIGateway
from diagrams.aws.analytics import Kinesis
from diagrams.aws.ml import Sagemaker, Textract
from diagrams.onprem.client import User
from diagrams.onprem.compute import Server
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.queue import Kafka
from diagrams.onprem.workflow import Airflow
from diagrams.onprem.mlops import Mlflow
from diagrams.elastic.elasticsearch import Elasticsearch
from diagrams.onprem.inmemory import Redis
from diagrams.onprem.monitoring import Datadog, Grafana
from diagrams.onprem.auth import Oauth2Proxy
from diagrams.onprem.iac import Terraform
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.container import Docker
from diagrams.onprem.network import Nginx
from diagrams.programming.framework import Fastapi, React
from diagrams.programming.language import Python, Typescript
from diagrams.saas.chat import Slack
from diagrams.saas.identity import Auth0
from diagrams.generic.blank import Blank
from diagrams.generic.storage import Storage

graph_attr = {
    "fontsize": "20",
    "bgcolor": "white",
    "pad": "0.6",
    "splines": "spline",
    "rankdir": "TB",
    "labelloc": "t",
    "label": "Credit Co-Pilot — Agentic Loan Underwriting Assistant",
    "fontname": "Helvetica-Bold",
}

node_attr = {"fontname": "Helvetica", "fontsize": "13"}
edge_attr = {"fontname": "Helvetica", "fontsize": "11", "color": "#444444"}

with Diagram(
    "Credit Co-Pilot Architecture",
    show=False,
    filename="/home/user/AI/credit_copilot_architecture",
    outformat=["png", "pdf"],
    direction="TB",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):

    with Cluster("Users & Channels", graph_attr={"bgcolor": "#F5FAFF"}):
        underwriter = User("Underwriter")
        loan_officer = User("Loan Officer")
        slack = Slack("Slack notifs")

    with Cluster("Presentation Layer", graph_attr={"bgcolor": "#FFF7E6"}):
        web = React("Next.js Web App\n(React + Tailwind)")
        ts = Typescript("Vercel AI SDK")

    with Cluster("Edge & Auth", graph_attr={"bgcolor": "#F0F7FF"}):
        gw = APIGateway("API Gateway")
        auth = Auth0("Auth0 / OIDC")
        oauth = Oauth2Proxy("OAuth2 / JWT")

    with Cluster("Application Services (EKS)", graph_attr={"bgcolor": "#EFFFF4"}):
        bff = Fastapi("BFF (FastAPI)")

        with Cluster("Agent Orchestrator", graph_attr={"bgcolor": "#E6F7FF"}):
            planner = Python("Planner\n(LangGraph)")
            executor = Python("Tool Executor")
            critic = Python("Critic Agent\n(Haiku 4.5)")
            guardrails = Python("Guardrails\n(PII / Injection)")

        with Cluster("Workflow & Events", graph_attr={"bgcolor": "#FFF0F6"}):
            temporal = Airflow("Temporal\nworkflows")
            kafka = Kafka("Kafka\nevent bus")
            redis = Redis("Redis cache")

    with Cluster("AI / ML Plane", graph_attr={"bgcolor": "#FFF1F0"}):
        claude_opus = Server("Claude Opus 4.7\n(Reasoning)")
        claude_haiku = Server("Claude Haiku 4.5\n(Utility)")
        textract = Textract("Document AI\n(Textract + Donut)")
        mlflow = Mlflow("MLflow Registry")
        sagemaker = Sagemaker("SageMaker\nPD / LGD / EAD")

    with Cluster("Knowledge & Data Plane", graph_attr={"bgcolor": "#F9F0FF"}):
        pg = PostgreSQL("Postgres 16\n(app + audit)")
        s3 = S3("S3 Docs\n(KMS encrypted)")
        vector = Elasticsearch("OpenSearch +\npgvector (RAG)")
        feast = Storage("Feast\nFeature Store")

    with Cluster("External APIs", graph_attr={"bgcolor": "#FFFBE6"}):
        bureau = Server("Credit Bureaus\nExperian / Equifax / TU")
        plaid = Server("Plaid\n(bank txns)")
        kyc = Server("KYC / AML\n(sanctions, PEP)")

    with Cluster("Policy & Decisioning", graph_attr={"bgcolor": "#E6FFFB"}):
        opa = Server("OPA / Rego\nDecision Engine")
        rules = Server("Camunda DMN\nPolicy Gates")

    with Cluster("Platform & Ops", graph_attr={"bgcolor": "#F0F0F0"}):
        eks = EKS("AWS EKS")
        tf = Terraform("Terraform")
        gha = GithubActions("GitHub Actions")
        dd = Datadog("Datadog + OTel")
        graf = Grafana("LangSmith /\nLangfuse traces")
        kms = KMS("KMS")
        secrets = SecretsManager("Secrets Mgr")

    # Flows
    [underwriter, loan_officer] >> Edge(color="#1f77b4") >> web
    web >> Edge(label="HTTPS") >> gw
    gw >> auth
    gw >> oauth >> bff
    bff >> Edge(color="#2ca02c", label="invoke agent") >> planner
    planner >> executor
    executor >> Edge(label="LLM call", style="bold", color="#d62728") >> claude_opus
    executor >> claude_haiku
    executor >> guardrails
    critic << Edge(label="review memo") << planner

    executor >> Edge(label="OCR / IDP") >> textract
    executor >> Edge(label="RAG") >> vector
    executor >> Edge(label="score") >> sagemaker
    sagemaker << mlflow
    executor >> Edge(label="policy gate") >> opa
    opa >> rules

    executor >> Edge(label="bureau pull") >> bureau
    executor >> plaid
    executor >> kyc

    bff >> temporal
    temporal >> kafka
    bff >> redis
    bff >> pg
    bff >> s3
    feast >> sagemaker

    # Ops
    eks >> Edge(style="dotted") >> [bff, planner, temporal]
    tf >> Edge(style="dotted") >> eks
    gha >> Edge(style="dotted") >> eks
    dd << Edge(style="dotted") << bff
    graf << Edge(style="dotted") << planner
    kms >> Edge(style="dotted") >> s3
    secrets >> Edge(style="dotted") >> bff

    slack << Edge(style="dotted", label="alerts") << dd

print("Diagram generated.")
