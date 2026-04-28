import logging
import re
import statistics
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import local
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import requests
from bs4 import BeautifulSoup

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
}

BASE_URL = "https://career.habr.com/vacancies"
REQUEST_TIMEOUT = 15
MAX_DETAIL_WORKERS = 4
DETAIL_REQUEST_DELAY = 0.2
SEARCH_REQUEST_DELAY = 0.5
MAX_SEARCH_PAGES = 2
MAX_VACANCIES_PER_ROLE = 18
MAX_EXAMPLES_PER_ROLE = 5
MIN_MARKET_DEMAND = 5
MIN_ANALYZED_VACANCIES = 3
TOP_DEMANDED_ROLES_LIMIT = 10

ROLE_CATALOG = [
    {
        "label_ru": "Python разработчик",
        "label_en": "Python Developer",
        "queries": ["python developer", "python разработчик", "python engineer"],
        "ai_keywords": ["Python", "FastAPI", "Django", "REST API", "SQL", "PostgreSQL", "Docker", "asyncio", "microservices", "pytest"],
        "title_keywords": ["python"],
    },
    {
        "label_ru": "Java разработчик",
        "label_en": "Java Developer",
        "queries": ["java developer", "java разработчик", "java engineer"],
        "ai_keywords": ["Java", "Spring Boot", "Hibernate", "Microservices", "REST API", "Kafka", "SQL", "Docker", "Kubernetes", "JUnit"],
        "title_keywords": ["java"],
        "title_excludes": ["javascript"],
    },
    {
        "label_ru": "Frontend разработчик",
        "label_en": "Frontend Developer",
        "queries": ["frontend developer", "frontend разработчик", "react developer", "javascript developer"],
        "ai_keywords": ["JavaScript", "TypeScript", "React", "Next.js", "Redux", "HTML", "CSS", "REST API", "GraphQL", "Webpack"],
        "title_keywords": ["frontend", "react", "javascript", "typescript", "front-end", "frontend разработчик", "web developer"],
    },
    {
        "label_ru": "Backend разработчик",
        "label_en": "Backend Developer",
        "queries": ["backend developer", "backend разработчик", "backend engineer"],
        "ai_keywords": ["Backend", "REST API", "Microservices", "SQL", "PostgreSQL", "Redis", "Kafka", "Docker", "Kubernetes", "CI/CD"],
        "title_keywords": ["backend", "back-end", "python developer", "java developer", "golang developer", "php developer", "node.js developer"],
    },
    {
        "label_ru": "Fullstack разработчик",
        "label_en": "Fullstack Developer",
        "queries": ["fullstack developer", "fullstack разработчик", "full stack developer"],
        "ai_keywords": ["JavaScript", "TypeScript", "React", "Node.js", "REST API", "SQL", "PostgreSQL", "Docker", "AWS", "CI/CD"],
        "title_keywords": ["fullstack", "full stack", "full-stack"],
    },
    {
        "label_ru": "DevOps инженер",
        "label_en": "DevOps Engineer",
        "queries": ["devops engineer", "devops инженер", "site reliability engineer", "sre"],
        "ai_keywords": ["DevOps", "CI/CD", "Docker", "Kubernetes", "Terraform", "Ansible", "AWS", "Linux", "Monitoring", "Infrastructure as Code"],
        "title_keywords": ["devops", "sre", "site reliability", "platform engineer"],
    },
    {
        "label_ru": "Data Scientist",
        "label_en": "Data Scientist",
        "queries": ["data scientist", "data science", "специалист по data science"],
        "ai_keywords": ["Python", "Machine Learning", "Pandas", "NumPy", "SQL", "A/B Testing", "Statistics", "scikit-learn", "Data Analysis", "Experiment Design"],
        "title_keywords": ["data scientist", "data science", "research scientist", "data analyst"],
    },
    {
        "label_ru": "ML инженер",
        "label_en": "Machine Learning Engineer",
        "queries": ["machine learning engineer", "ml engineer", "инженер машинного обучения"],
        "ai_keywords": ["Machine Learning", "Python", "PyTorch", "TensorFlow", "MLOps", "Docker", "Kubernetes", "Feature Engineering", "Model Deployment", "Airflow"],
        "title_keywords": ["machine learning", "ml engineer", "mlops", "ai engineer", "инженер машинного обучения"],
    },
    {
        "label_ru": "QA инженер",
        "label_en": "QA Engineer",
        "queries": ["qa engineer", "qa инженер", "test engineer", "тестировщик"],
        "ai_keywords": ["QA", "Test Automation", "Selenium", "Playwright", "API Testing", "Postman", "pytest", "CI/CD", "Regression Testing", "Test Cases"],
        "title_keywords": ["qa", "quality assurance", "test engineer", "тестировщик", "automation qa", "manual qa"],
    },
    {
        "label_ru": "Android разработчик",
        "label_en": "Android Developer",
        "queries": ["android developer", "android разработчик"],
        "ai_keywords": ["Android", "Kotlin", "Java", "Jetpack Compose", "MVVM", "REST API", "Coroutines", "Room", "Gradle", "Firebase"],
        "title_keywords": ["android"],
    },
    {
        "label_ru": "iOS разработчик",
        "label_en": "iOS Developer",
        "queries": ["ios developer", "ios разработчик"],
        "ai_keywords": ["iOS", "Swift", "UIKit", "SwiftUI", "MVVM", "REST API", "Core Data", "Xcode", "Unit Testing", "App Store"],
        "title_keywords": ["ios", "iphone", "swift"],
    },
    {
        "label_ru": "Product Manager",
        "label_en": "Product Manager",
        "queries": ["product manager", "продакт менеджер", "менеджер продукта"],
        "ai_keywords": ["Product Management", "Roadmap", "Backlog", "User Research", "A/B Testing", "Analytics", "Stakeholder Management", "Go-to-Market", "Jira", "SQL"],
        "title_keywords": ["product manager", "product owner", "продакт", "менеджер продукта"],
    },
    {
        "label_ru": "Тимлид / Руководитель команды разработки",
        "label_en": "Team Lead / Development Team Lead",
        "queries": ["team lead", "тимлид", "руководитель команды разработки", "руководитель группы разработки"],
        "ai_keywords": ["Team Lead", "People Management", "Team Leadership", "Agile", "Scrum", "Hiring", "Mentoring", "Delivery Management", "Roadmap Planning", "Cross-functional Communication"],
        "title_keywords": ["team lead", "тимлид", "руководитель команды разработки", "руководитель группы разработки", "teamlead"],
    },
    {
        "label_ru": "Техлид / Технический руководитель",
        "label_en": "Tech Lead / Technical Lead",
        "queries": ["tech lead", "technical lead", "техлид", "технический руководитель", "технический лидер"],
        "ai_keywords": ["Tech Lead", "Technical Leadership", "System Design", "Architecture", "Code Review", "Mentoring", "Highload Systems", "Microservices", "Stakeholder Management", "Delivery"],
        "title_keywords": ["tech lead", "technical lead", "техлид", "технический руководитель", "технический лидер"],
    },
    {
        "label_ru": "Engineering Manager / Руководитель разработки",
        "label_en": "Engineering Manager / Head of Engineering",
        "queries": ["engineering manager", "руководитель разработки", "head of engineering", "development manager"],
        "ai_keywords": ["Engineering Manager", "People Management", "Technical Leadership", "System Design", "Architecture", "Performance Reviews", "Hiring", "Mentoring", "Delivery Management", "Stakeholder Management"],
        "title_keywords": ["engineering manager", "head of engineering", "руководитель разработки", "development manager"],
    },
    {
        "label_ru": "Архитектор решений / Software Architect",
        "label_en": "Solution Architect / Software Architect",
        "queries": ["solution architect", "software architect", "архитектор решений", "системный архитектор"],
        "ai_keywords": ["Solution Architect", "Software Architect", "System Design", "Architecture", "Integration", "UML", "C4 Model", "Technical Documentation", "Highload Systems", "Stakeholder Management"],
        "title_keywords": ["solution architect", "software architect", "архитектор решений", "системный архитектор", "технический архитектор"],
    },
    {
        "label_ru": "Full-stack разработчик с уклоном в AI",
        "label_en": "Full-stack Developer (AI-focused)",
        "queries": ["full-stack developer ai", "fullstack developer ai", "ai developer", "llm engineer", "generative ai engineer"],
        "ai_keywords": ["LLM", "Generative AI", "Prompt Engineering", "RAG", "OpenAI API", "Python", "TypeScript", "React", "Vector Database", "AI Agents"],
        "title_keywords": ["full-stack", "fullstack", "full stack", "ai developer", "llm engineer", "generative ai", "ai engineer"],
    },
]

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
THREAD_LOCAL = local()

SKILL_MAPPING = {
    "python": ["python", "django", "flask", "fastapi", "sqlalchemy", "pandas", "numpy", "scikit-learn", "pytest"],
    "java": ["java", "spring", "spring boot", "hibernate", "maven", "gradle", "kotlin", "scala"],
    "javascript": ["javascript", "typescript", "node.js", "nodejs", "express", "nest.js", "nestjs", "react", "vue", "angular", "jquery"],
    "database": ["sql", "postgresql", "postgres", "mysql", "mongodb", "redis", "elasticsearch", "cassandra", "clickhouse"],
    "devops": ["docker", "kubernetes", "k8s", "jenkins", "gitlab", "github actions", "terraform", "ansible", "linux", "bash", "nginx"],
    "cloud": ["aws", "azure", "gcp", "google cloud", "yandex cloud", "openstack"],
    "qa": ["pytest", "junit", "selenium", "postman", "jmeter", "testrail", "allure", "cypress", "playwright"],
    "methodology": ["agile", "scrum", "kanban", "jira", "confluence", "trello"],
    "mobile": ["android", "ios", "swift", "kotlin", "react native", "flutter", "xamarin"],
    "datascience": ["tensorflow", "pytorch", "keras", "spark", "hadoop", "airflow", "ml", "machine learning", "deep learning", "nlp"],
    "frontend": ["html", "css", "sass", "less", "webpack", "vite", "tailwind", "bootstrap", "next.js", "nuxt"],
    "backend": ["rest", "graphql", "grpc", "rabbitmq", "kafka", "celery", "microservices", "redis"],
    "security": ["owasp", "ssl", "oauth", "jwt", "penetration testing", "vulnerability assessment"],
    "vcs": ["git", "github", "gitlab", "bitbucket"],
    "analytics": ["power bi", "tableau", "superset", "dbt"],
}

ALL_SKILLS = sorted({skill for skills in SKILL_MAPPING.values() for skill in skills})
SKILL_PATTERNS = {}
SKILL_ALIAS_TO_CANONICAL = {}
SALARY_NUMBER_PATTERN = re.compile(r"\d[\d\s\xa0]*")

for skill in ALL_SKILLS:
    variants = {
        skill,
        skill.replace("-", " "),
        skill.replace(" ", "-"),
    }
    SKILL_PATTERNS[skill] = [re.compile(r"\b" + re.escape(variant) + r"\b") for variant in variants]
    for variant in variants:
        normalized_variant = re.sub(r"[-\s]+", " ", variant.strip().lower())
        SKILL_ALIAS_TO_CANONICAL[normalized_variant] = skill


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def get_thread_session() -> requests.Session:
    session = getattr(THREAD_LOCAL, "session", None)
    if session is None:
        session = create_session()
        THREAD_LOCAL.session = session
    return session


def fetch_page(session: requests.Session, url: str, params: Optional[Dict] = None) -> BeautifulSoup:
    resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def normalize_text_token(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def normalize_skill_name(skill: str) -> str:
    token = re.sub(r"[-\s]+", " ", skill.strip().lower())
    return SKILL_ALIAS_TO_CANONICAL.get(token, token)


def normalize_title(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def role_matches_title(role: Dict, title: str) -> bool:
    normalized_title = normalize_title(title)
    include_keywords = role.get("title_keywords", [])
    exclude_keywords = role.get("title_excludes", [])

    if exclude_keywords and any(keyword.lower() in normalized_title for keyword in exclude_keywords):
        return False

    if include_keywords:
        return any(keyword.lower() in normalized_title for keyword in include_keywords)

    return True


def extract_skills_from_text(text: str) -> List[str]:
    if not text:
        return []

    text_lower = text.lower()
    found_skills = set()

    for skill, patterns in SKILL_PATTERNS.items():
        if any(pattern.search(text_lower) for pattern in patterns):
            found_skills.add(skill)

    return sorted(found_skills)


def extract_explicit_skills(soup: BeautifulSoup) -> List[str]:
    selectors = [
        'a[class*="tag"]',
        'span[class*="tag"]',
        'a[class*="skill"]',
        'span[class*="skill"]',
        'li[class*="skill"]',
    ]
    raw_skills = set()

    for selector in selectors:
        for elem in soup.select(selector):
            text = normalize_text_token(elem.get_text(" ", strip=True))
            if 1 < len(text) <= 40 and re.search(r"[a-zA-Zа-яА-Я0-9]", text):
                raw_skills.add(normalize_skill_name(text))

    return sorted(raw_skills)


def find_vacancy_cards(soup: BeautifulSoup) -> List[BeautifulSoup]:
    cards = soup.find_all("div", class_="vacancy-card")
    if not cards:
        cards = soup.find_all("div", class_="job-card")
    if not cards:
        cards = soup.find_all("article")
    return cards


def parse_salary(salary_text: str) -> Optional[Dict]:
    if not salary_text or salary_text == "не указана":
        return None

    numbers = [int(re.sub(r"\D", "", match)) for match in SALARY_NUMBER_PATTERN.findall(salary_text)]
    if not numbers:
        return None

    salary_lower = salary_text.lower()
    currency = "RUB"
    if "$" in salary_text or "usd" in salary_lower:
        currency = "USD"
    elif "€" in salary_text or "eur" in salary_lower:
        currency = "EUR"

    if len(numbers) == 1:
        salary_min, salary_max = numbers[0], numbers[0]
    else:
        salary_min, salary_max = min(numbers), max(numbers)

    return {
        "min": salary_min,
        "max": salary_max,
        "currency": currency,
        "raw": salary_text,
    }


def summarize_salaries(vacancies: List[Dict]) -> List[str]:
    buckets: Dict[str, List[int]] = {}

    for vacancy in vacancies:
        parsed = vacancy.get("salary_parsed")
        if not parsed:
            continue
        values = buckets.setdefault(parsed["currency"], [])
        values.append(parsed["min"])
        values.append(parsed["max"])

    if not buckets:
        return ["нет данных"]

    summaries = []
    for currency, values in buckets.items():
        summaries.append(
            f"{currency}: min {min(values):,}, median {int(statistics.median(values)):,}, max {max(values):,}".replace(",", " ")
        )
    return summaries


def calculate_keyword_coverage(skills: List[str], ai_keywords: List[str]) -> Tuple[List[str], List[str]]:
    normalized_skills = {normalize_skill_name(skill) for skill in skills}
    matched = []
    missing = []

    for keyword in ai_keywords:
        normalized_keyword = normalize_skill_name(keyword)
        if normalized_keyword in normalized_skills:
            matched.append(keyword)
        else:
            missing.append(keyword)

    return matched, missing


def get_vacancies_count(session: requests.Session, keyword: str) -> int:
    params = {"q": keyword, "page": 1}

    try:
        soup = fetch_page(session, BASE_URL, params=params)
        count_elem = soup.find("div", class_="vacancy-search__header-count")
        if count_elem:
            numbers = re.findall(r"\d+", count_elem.text)
            if numbers:
                return int(numbers[0])

        return len(find_vacancy_cards(soup))
    except requests.RequestException as e:
        logger.warning("Не удалось получить количество вакансий для '%s': %s", keyword, e)
        return 0
    except Exception as e:
        logger.warning("Ошибка при разборе списка вакансий для '%s': %s", keyword, e)
        return 0


def get_vacancy_details_robust(vacancy_url: str, title: str = "") -> Dict:
    result = {"description": "", "requirements": "", "skills_from_title": [], "skills_from_page": []}

    if title:
        result["skills_from_title"] = extract_skills_from_text(title)

    try:
        time.sleep(DETAIL_REQUEST_DELAY)
        soup = fetch_page(get_thread_session(), vacancy_url)

        selectors = [
            "div.job-description",
            "div.vacancy-description",
            "div.content",
            "div.vacancy__description",
            "article",
            'div[class*="description"]',
            'div[class*="Description"]',
            'div[class*="content"]',
        ]

        description_text = ""
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                description_text = elem.get_text(separator=" ", strip=True)
                if len(description_text) > 100:
                    break

        if not description_text or len(description_text) < 100:
            for div in soup.find_all("div"):
                div_text = div.get_text(separator=" ", strip=True)
                if 200 < len(div_text) < 5000:
                    description_text = div_text
                    break

        result["description"] = description_text

        requirements_elem = soup.find("div", class_="job-requirements")
        if not requirements_elem:
            requirements_elem = soup.find("div", class_="vacancy-requirements")
        if requirements_elem:
            result["requirements"] = requirements_elem.get_text(separator=" ", strip=True)

        result["skills_from_page"] = extract_explicit_skills(soup)
    except requests.RequestException as e:
        logger.warning("Не удалось загрузить вакансию %s: %s", vacancy_url, e)
    except Exception as e:
        logger.warning("Ошибка при парсинге вакансии %s: %s", vacancy_url, e)

    return result


def parse_vacancy_card(card: BeautifulSoup, role: Dict) -> Optional[Dict]:
    title_elem = (
        card.find("a", class_="vacancy-card__title-link")
        or card.find("a", class_="job__title-link")
        or card.find("a", href=re.compile(r"/vacancies/\d+"))
    )
    if not title_elem:
        return None

    title = title_elem.text.strip() if title_elem else "Не указано"
    if not role_matches_title(role, title):
        return None

    href = title_elem.get("href", "")
    url = href if href.startswith("http") else f"https://career.habr.com{href}"

    company_elem = (
        card.find("div", class_="vacancy-card__company-title")
        or card.find("div", class_="job__company")
        or card.find("span", class_="company-name")
    )
    company = company_elem.text.strip() if company_elem else "Не указана"

    city_elem = (
        card.find("span", class_="vacancy-card__meta-location")
        or card.find("span", class_="job__location")
        or card.find("div", class_="location")
    )
    city = city_elem.text.strip() if city_elem else "Не указан"

    salary_elem = (
        card.find("div", class_="vacancy-card__salary")
        or card.find("div", class_="job__salary")
    )
    salary = salary_elem.text.strip() if salary_elem else "не указана"

    return {
        "title": title,
        "company": company,
        "city": city,
        "salary": salary,
        "salary_parsed": parse_salary(salary),
        "url": url,
        "skills": [],
    }


def collect_role_vacancies(session: requests.Session, role: Dict, queries: List[str], limit: int) -> Tuple[List[Dict], int, Dict[str, int]]:
    vacancy_map: Dict[str, Dict] = {}
    query_counts: Dict[str, int] = {}

    for query in queries:
        query_counts[query] = get_vacancies_count(session, query)

        for page in range(1, MAX_SEARCH_PAGES + 1):
            try:
                soup = fetch_page(session, BASE_URL, params={"q": query, "page": page})
            except requests.RequestException as e:
                logger.warning("Не удалось получить страницу %s для '%s': %s", page, query, e)
                break

            cards = find_vacancy_cards(soup)
            if not cards:
                break

            for card in cards:
                vacancy = parse_vacancy_card(card, role)
                if vacancy and vacancy["url"] not in vacancy_map:
                    vacancy_map[vacancy["url"]] = vacancy
                if len(vacancy_map) >= limit:
                    break

            if len(vacancy_map) >= limit:
                break

            time.sleep(SEARCH_REQUEST_DELAY)

        if len(vacancy_map) >= limit:
            break

    estimated_market_count = max(query_counts.values(), default=0)
    return list(vacancy_map.values()), estimated_market_count, query_counts


def enrich_vacancies_with_details(vacancies: List[Dict]) -> Counter:
    skill_counter = Counter()

    with ThreadPoolExecutor(max_workers=MAX_DETAIL_WORKERS) as executor:
        future_to_row = {
            executor.submit(get_vacancy_details_robust, row["url"], row["title"]): row
            for row in vacancies
        }

        for future in as_completed(future_to_row):
            row = future_to_row[future]
            details = future.result()

            full_text = f"{row['title']} {details.get('description', '')} {details.get('requirements', '')}"
            skills = set(extract_skills_from_text(full_text))
            skills.update(details.get("skills_from_title", []))
            skills.update(details.get("skills_from_page", []))

            row["skills"] = sorted(skills)
            row["description"] = details.get("description", "")
            row["requirements"] = details.get("requirements", "")
            for skill in row["skills"]:
                skill_counter[skill] += 1

    return skill_counter


def normalize_multiline_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def is_demanded_role(result: Dict) -> bool:
    return result["vacancies"] >= MIN_MARKET_DEMAND and result["analyzed_count"] >= MIN_ANALYZED_VACANCIES


def filter_demanded_results(results: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    demanded = [result for result in results if is_demanded_role(result)]
    excluded = [result for result in results if not is_demanded_role(result)]

    demanded.sort(key=lambda item: (item["vacancies"], item["analyzed_count"]), reverse=True)
    excluded.sort(key=lambda item: (item["vacancies"], item["analyzed_count"]), reverse=True)

    return demanded[:TOP_DEMANDED_ROLES_LIMIT], excluded


def analyze_demand() -> Tuple[List[Dict], List[Dict], List[Dict]]:
    results = []
    total = len(ROLE_CATALOG)

    print("\n" + "=" * 60)
    print("📊 АНАЛИЗ РОЛЕЙ, НАВЫКОВ И ЗАРПЛАТ В IT")
    print("=" * 60)

    with create_session() as session:
        for index, role in enumerate(ROLE_CATALOG, 1):
            role_name = f"{role['label_ru']} / {role['label_en']}"
            print(f"\n[{index}/{total}] {role_name}...")

            vacancies, estimated_market_count, query_counts = collect_role_vacancies(
                session=session,
                role=role,
                queries=role["queries"],
                limit=MAX_VACANCIES_PER_ROLE,
            )
            print(f"  Оценка спроса по лучшему запросу: {estimated_market_count}")
            print(f"  Уникальных вакансий для анализа: {len(vacancies)}")

            skill_counter = enrich_vacancies_with_details(vacancies) if vacancies else Counter()
            print(f"  Найдено уникальных навыков: {len(skill_counter)}")
            matched_keywords, missing_keywords = calculate_keyword_coverage(
                [skill for skill, _ in skill_counter.most_common()],
                role.get("ai_keywords", []),
            )

            results.append(
                {
                    "name": role_name,
                    "name_ru": role["label_ru"],
                    "name_en": role["label_en"],
                    "queries": role["queries"],
                    "ai_keywords": role.get("ai_keywords", []),
                    "vacancies": estimated_market_count,
                    "query_counts": query_counts,
                    "examples": vacancies[:MAX_EXAMPLES_PER_ROLE],
                    "skills_ranked": [skill for skill, _ in skill_counter.most_common()],
                    "all_skills": dict(skill_counter.most_common()),
                    "matched_ai_keywords": matched_keywords,
                    "missing_ai_keywords": missing_keywords,
                    "salary_summary": summarize_salaries(vacancies),
                    "analyzed_count": len(vacancies),
                }
            )

            time.sleep(SEARCH_REQUEST_DELAY)

    all_results = sorted(results, key=lambda item: (item["vacancies"], item["analyzed_count"]), reverse=True)
    demanded_results, excluded_results = filter_demanded_results(all_results)

    print("\n" + "=" * 60)
    print("РЫНОЧНЫЙ ФИЛЬТР")
    print("=" * 60)
    print(
        f"В итоговый топ попадают роли с оценкой спроса >= {MIN_MARKET_DEMAND} "
        f"и минимум {MIN_ANALYZED_VACANCIES} уникальными вакансиями."
    )
    print(f"Прошли фильтр: {len(demanded_results)} | Исключены как слишком слабые/нишевые: {len(excluded_results)}")

    return demanded_results, all_results, excluded_results


def print_results(results: List[Dict]) -> None:
    print("\n" + "🏆" * 25)
    print("ВОСТРЕБОВАННЫЕ IT-РОЛИ")
    print("🏆" * 25)

    print(f"\n{'№':<3} {'Роль':<40} {'Вакансий':<10}")
    print("-" * 70)
    for index, item in enumerate(results, 1):
        name = item["name"][:39]
        print(f"{index:<3} {name:<40} {item['vacancies']:>10}")

    print("\n" + "📊" * 25)
    print("НАВЫКИ И ЗАРПЛАТЫ ПО РОЛЯМ")
    print("📊" * 25)

    for index, item in enumerate(results, 1):
        print(f"\n{'=' * 70}")
        print(f"{index}. {item['name']}")
        print(f"   Оценка спроса: {item['vacancies']} | Проанализировано вакансий: {item['analyzed_count']}")
        print(f"   Запросы: {', '.join(item['queries'])}")
        print(f"   ATS/AI keywords: {', '.join(item['ai_keywords'])}")
        print(f"   Подтверждено рынком: {', '.join(item['matched_ai_keywords']) if item['matched_ai_keywords'] else 'нет совпадений'}")
        print(f"   Не найдено в выборке: {', '.join(item['missing_ai_keywords']) if item['missing_ai_keywords'] else 'нет'}")
        print(f"   Разбивка по запросам: {', '.join(f'{query}={count}' for query, count in item['query_counts'].items())}")
        print(f"   Зарплаты: {'; '.join(item['salary_summary'])}")
        print("-" * 70)

        if item["skills_ranked"]:
            print("\n   🔧 ПОЛНЫЙ СПИСОК НАВЫКОВ:")
            for skill in item["skills_ranked"]:
                count = item["all_skills"].get(skill, 0)
                print(f"      - {skill} ({count})")
        else:
            print("\n   ⚠️ Навыки не найдены")

        if item["examples"]:
            print("\n   📌 ПРИМЕРЫ ВАКАНСИЙ:")
            for vacancy in item["examples"]:
                print(f"\n      • {vacancy['title']}")
                print(f"        🏢 {vacancy['company']} | 📍 {vacancy['city']} | 💰 {vacancy['salary']}")
                if vacancy.get("skills"):
                    print(f"        🛠️ {', '.join(vacancy['skills'])}")
                if vacancy.get("requirements"):
                    print(f"        📋 Требования: {normalize_multiline_text(vacancy['requirements'])}")
                elif vacancy.get("description"):
                    print(f"        📄 Описание: {normalize_multiline_text(vacancy['description'])}")
        else:
            print("\n   📌 Примеры вакансий не найдены")


def save_to_file(results: List[Dict]) -> None:
    from datetime import datetime

    filename = f"it_market_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    with open(filename, "w", encoding="utf-8") as file:
        file.write("=" * 80 + "\n")
        file.write("ОТЧЕТ: IT-РОЛИ, НАВЫКИ И ЗАРПЛАТЫ\n")
        file.write(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        file.write("Источник: Habr Career\n")
        file.write("=" * 80 + "\n\n")

        for index, item in enumerate(results, 1):
            file.write(f"{index}. {item['name']}\n")
            file.write(f"   Оценка спроса: {item['vacancies']}\n")
            file.write(f"   Проанализировано вакансий: {item['analyzed_count']}\n")
            file.write(f"   Запросы: {', '.join(item['queries'])}\n")
            file.write(f"   ATS/AI keywords: {', '.join(item['ai_keywords'])}\n")
            file.write(f"   Подтверждено рынком: {', '.join(item['matched_ai_keywords']) if item['matched_ai_keywords'] else 'нет совпадений'}\n")
            file.write(f"   Не найдено в выборке: {', '.join(item['missing_ai_keywords']) if item['missing_ai_keywords'] else 'нет'}\n")
            file.write(f"   Разбивка по запросам: {', '.join(f'{query}={count}' for query, count in item['query_counts'].items())}\n")
            file.write(f"   Зарплаты: {'; '.join(item['salary_summary'])}\n")

            if item["skills_ranked"]:
                file.write("\n   Полный список навыков:\n")
                for skill in item["skills_ranked"]:
                    count = item["all_skills"].get(skill, 0)
                    file.write(f"      - {skill} ({count})\n")
            else:
                file.write("\n   Навыки не найдены\n")

            if item["examples"]:
                file.write("\n   Примеры вакансий:\n")
                for vacancy in item["examples"]:
                    file.write(f"      • {vacancy['title']}\n")
                    file.write(f"        Компания: {vacancy['company']} | Город: {vacancy['city']} | Зарплата: {vacancy['salary']}\n")
                    if vacancy.get("skills"):
                        file.write(f"        Навыки: {', '.join(vacancy['skills'])}\n")
                    if vacancy.get("requirements"):
                        file.write(f"        Требования: {normalize_multiline_text(vacancy['requirements'])}\n")
                    elif vacancy.get("description"):
                        file.write(f"        Описание: {normalize_multiline_text(vacancy['description'])}\n")
                    file.write(f"        Ссылка: {vacancy['url']}\n")
            file.write("\n" + "-" * 80 + "\n\n")

    print(f"\n💾 Полный отчет сохранен в файл: {filename}")


def excel_column_name(index: int) -> str:
    result = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def escape_excel(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    return escape(text)


def build_sheet_xml(headers: List[str], rows: List[List[object]], widths: List[int], freeze_top: bool = True) -> str:
    header_cells = []
    for col_index, header in enumerate(headers, 1):
        cell_ref = f"{excel_column_name(col_index)}1"
        header_cells.append(
            f'<c r="{cell_ref}" s="1" t="inlineStr"><is><t>{escape_excel(header)}</t></is></c>'
        )

    row_xml = [f'<row r="1" spans="1:{len(headers)}">{"".join(header_cells)}</row>']

    for row_index, row in enumerate(rows, 2):
        cells = []
        for col_index, value in enumerate(row, 1):
            cell_ref = f"{excel_column_name(col_index)}{row_index}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{cell_ref}"><v>{value}</v></c>')
            else:
                cells.append(
                    f'<c r="{cell_ref}" t="inlineStr"><is><t xml:space="preserve">{escape_excel(value)}</t></is></c>'
                )
        row_xml.append(f'<row r="{row_index}" spans="1:{len(headers)}">{"".join(cells)}</row>')

    cols_xml = []
    for index, width in enumerate(widths, 1):
        cols_xml.append(f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>')

    auto_filter_ref = f"A1:{excel_column_name(len(headers))}{max(len(rows) + 1, 1)}"
    pane_xml = '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>' if freeze_top else ""

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetViews>
    <sheetView workbookViewId="0">{pane_xml}</sheetView>
  </sheetViews>
  <cols>{"".join(cols_xml)}</cols>
  <sheetData>{"".join(row_xml)}</sheetData>
  <autoFilter ref="{auto_filter_ref}"/>
</worksheet>'''


def save_to_excel(results: List[Dict]) -> None:
    from datetime import datetime

    filename = f"it_market_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    summary_headers = [
        "Роль (RU)",
        "Роль (EN)",
        "Оценка спроса",
        "Проанализировано вакансий",
        "Поисковые запросы",
        "Разбивка по запросам",
        "Сводка по зарплатам",
        "ATS/AI ключевики",
        "Подтверждено рынком",
        "Не найдено в выборке",
    ]
    summary_rows = []
    for item in results:
        summary_rows.append([
            item["name_ru"],
            item["name_en"],
            item["vacancies"],
            item["analyzed_count"],
            ", ".join(item["queries"]),
            ", ".join(f"{query}={count}" for query, count in item["query_counts"].items()),
            "; ".join(item["salary_summary"]),
            ", ".join(item["ai_keywords"]),
            ", ".join(item["matched_ai_keywords"]),
            ", ".join(item["missing_ai_keywords"]),
        ])

    vacancies_headers = [
        "Роль",
        "Название вакансии",
        "Компания",
        "Город",
        "Зарплата как в вакансии",
        "Зарплата от",
        "Зарплата до",
        "Валюта",
        "Навыки",
        "Требования",
        "Описание",
        "Ссылка",
    ]
    vacancies_rows = []
    for item in results:
        for vacancy in item["examples"]:
            salary = vacancy.get("salary_parsed") or {}
            vacancies_rows.append([
                item["name"],
                vacancy.get("title", ""),
                vacancy.get("company", ""),
                vacancy.get("city", ""),
                vacancy.get("salary", ""),
                salary.get("min", ""),
                salary.get("max", ""),
                salary.get("currency", ""),
                ", ".join(vacancy.get("skills", [])),
                normalize_multiline_text(vacancy.get("requirements", "")),
                normalize_multiline_text(vacancy.get("description", "")),
                vacancy.get("url", ""),
            ])

    skills_headers = ["Role", "Skill", "Count"]
    skills_headers = ["Роль", "Навык", "Частота"]
    skills_rows = []
    for item in results:
        for skill, count in item["all_skills"].items():
            skills_rows.append([item["name"], skill, count])

    workbook_files = {
        "[Content_Types].xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>''',
        "_rels/.rels": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>''',
        "docProps/app.xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>PythonHiringAnalyzer</Application>
</Properties>''',
        "docProps/core.xml": f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}</dcterms:modified>
  <dc:title>IT Market Report</dc:title>
</cp:coreProperties>''',
        "xl/workbook.xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Сводка" sheetId="1" r:id="rId1"/>
    <sheet name="Вакансии" sheetId="2" r:id="rId2"/>
    <sheet name="Навыки" sheetId="3" r:id="rId3"/>
  </sheets>
</workbook>''',
        "xl/_rels/workbook.xml.rels": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>''',
        "xl/styles.xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
  </fonts>
  <fills count="3">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="1">
    <border><left/><right/><top/><bottom/><diagonal/></border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="2">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
  </cellXfs>
</styleSheet>''',
        "xl/worksheets/sheet1.xml": build_sheet_xml(
            summary_headers,
            summary_rows,
            [24, 28, 14, 16, 40, 32, 28, 40, 30, 30],
        ),
        "xl/worksheets/sheet2.xml": build_sheet_xml(
            vacancies_headers,
            vacancies_rows,
            [34, 42, 24, 18, 18, 12, 12, 10, 40, 90, 90, 50],
        ),
        "xl/worksheets/sheet3.xml": build_sheet_xml(
            skills_headers,
            skills_rows,
            [34, 24, 10],
        ),
    }

    with ZipFile(filename, "w", compression=ZIP_DEFLATED) as workbook:
        for path, content in workbook_files.items():
            workbook.writestr(path, content)

    print(f"💾 Excel-отчет сохранен в файл: {filename}")


def main() -> None:
    print("\n" + "🚀" * 25)
    print("ПАРСЕР IT-ВАКАНСИЙ: РОЛИ, НАВЫКИ, ЗАРПЛАТЫ")
    print("Источник: Habr Career")
    print("🚀" * 25)

    try:
        demanded_results, all_results, excluded_results = analyze_demand()
        if not all_results:
            print("\n❌ Не удалось получить данные. Проверьте интернет-соединение.")
            return

        print_results(demanded_results)
        if excluded_results:
            print(f"\nℹ️ В выгрузки включены все роли, в том числе {len(excluded_results)} ролей вне основного рыночного топа.")
        save_to_file(all_results)
        save_to_excel(all_results)

        print("\n" + "✅" * 25)
        print("ГОТОВО! Анализ рынка IT завершен.")
        print("✅" * 25)
    except KeyboardInterrupt:
        print("\n\n⏹️ Прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")


if __name__ == "__main__":
    main()
