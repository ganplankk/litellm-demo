# Windows WSL2 · LiteLLM · PostgreSQL · Claude Desktop 실습

이 가이드는 **Windows용 Claude Desktop**을 채팅 클라이언트로 사용한다. CLI인 Claude Code와는 설정 위치가 다르다. 모델 제공자는 **AWS Bedrock**으로 가정한다. 로컬 PC에서 실행하는 것은 게이트웨이와 DB이며, Claude 모델 자체를 로컬에 설치하는 구성은 아니다.

목표: Desktop에서 보낸 메시지가 LiteLLM을 거쳐 Bedrock으로 전달되고, LiteLLM에서 사용한 키·모델·사용량을 확인한다. HTTP 프록시 환경변수를 설정하는 방식이 아니라, 클라이언트의 LLM API 주소를 LiteLLM으로 지정한다.

| 구성 요소 | 실행 위치 | 역할 |
| --- | --- | --- |
| Claude Desktop | Windows | 채팅 화면, LiteLLM API 호출 |
| Docker Desktop | Windows, WSL2 엔진 | 컨테이너 실행 |
| LiteLLM | Docker 컨테이너 | 키 인증, 모델 호출 중계, 사용량 관리 |
| PostgreSQL 16 | Docker 컨테이너 | 키·설정·사용량 등 관리 데이터 저장 |
| Claude 모델 | AWS Bedrock | 실제 추론 처리, API 사용료 발생 |

LiteLLM은 `127.0.0.1:4000`으로만 공개하며 PostgreSQL은 호스트 포트를 열지 않는다. DB 파일은 Docker named volume에 보관한다. 현재의 일반 채팅 실습에는 MCP 설정이 필요 없다.

## 1. 준비

- Windows의 WSL2 + Ubuntu
- Docker Desktop: **Settings → General → Use the WSL 2 based engine**, **Resources → WSL Integration → 사용할 Ubuntu 활성화**
- Windows용 Claude Desktop: **Configure Third-Party Inference** 기능을 제공하는 버전
- WSL 안의 Python 3, curl, unzip, AWS CLI v2
- AWS 계정과 Bedrock Claude 호출 권한이 있는 AWS CLI 프로필

Docker Desktop의 WSL Integration을 사용할 때 Ubuntu에 별도 Docker Engine을 중복 설치할 필요는 없다. 이 패키지는 컨테이너 이미지를 사용하므로 호스트에 `pip install litellm`도 필요 없다.

이후 명령은 별도 표시가 없으면 **WSL Ubuntu 터미널**에서 실행한다.

```bash
docker version
docker compose version
python3 --version
aws --version
```

`docker version`에 Client와 Server가 모두 나와야 한다. Python·curl·unzip이 없다면:

```bash
sudo apt update
sudo apt install -y python3 curl unzip
```

AWS CLI가 없다면 [AWS CLI v2 설치 안내](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)의 Linux 절차로 **WSL 안에** 설치한다. 일반 Intel/AMD PC는 x86_64, ARM Windows PC의 WSL은 aarch64 패키지를 확인한다.

## 2. 압축 풀기와 초기 설정

다운로드한 ZIP 안에는 `litellm-local-lab/` 폴더가 있다. 이를 WSL의 `~/projects/` 아래에 둔다. Windows 탐색기에서 `\\wsl.localhost\Ubuntu\home\본인의리눅스계정\projects`에 접근해 복사할 수도 있다. 배포판 이름이 다르면 `Ubuntu` 부분을 바꾼다.

터미널로 압축을 풀려면 먼저 다음 명령을 실행한다. 파일 경로를 물으면 실제 ZIP 경로(예: `/mnt/c/Users/사용자명/Downloads/litellm-local-lab.zip`)를 입력한다.

```bash
mkdir -p ~/projects
read -r -p "다운로드한 ZIP의 WSL 경로: " lab_zip_path
unzip "$lab_zip_path" -d ~/projects
cd ~/projects/litellm-local-lab
python3 scripts/init_env.py
```

이 스크립트는 `.env`에 고유한 DB 비밀번호·관리자 비밀번호·master key·salt key를 생성한다. 기존 `.env`가 있으면 유지한다. 생성된 `.env`와 `.aws.env`는 공유하거나 Git에 올리지 않는다. DB를 유지한 채 비밀번호나 salt를 임의로 다시 생성하면 기존 데이터 사용에 문제가 생길 수 있다.

파일 구성:

| 파일 | 용도 |
| --- | --- |
| `compose.yaml` | LiteLLM + PostgreSQL 실행 |
| `config.yaml` | `claude-lab`이라는 모델 별칭 등록 |
| `.env.example` | 설정 템플릿, 실제 비밀값 없음 |
| `.env` | 실행 시 생성되는 로컬 설정·비밀값 |
| `.aws.env` | AWS CLI에서 내보낸 현재 AWS 자격 증명 |
| `scripts/` | 초기 설정, AWS 인증 전달, 이미지 고정, API 테스트 |

## 3. AWS 인증과 사용할 모델 선택

기존 WSL AWS 프로필이 있다면 그 이름을 사용한다. 아래 `litellm-lab`은 예시 이름이다. Windows에 만든 프로필이 WSL에 자동으로 생기는 것은 아니다.

IAM Identity Center를 사용하는 계정이고 새 프로필이 필요할 때만:

```bash
aws configure sso --profile litellm-lab
aws sso login --profile litellm-lab
```

SSO 시작 URL·리전·계정·역할은 실제 조직 설정을 사용한다. SSO를 사용하지 않는 경우에는 기존에 승인된 AWS CLI 인증 방식으로 프로필을 준비한다. 이 실습을 위해 root 액세스 키나 AdministratorAccess가 필요한 것은 아니다.

인증 확인:

```bash
aws sts get-caller-identity --profile litellm-lab
```

성공하면 계정과 호출 주체가 나온다. 이어서 사용할 리전에서 Claude inference profile 목록을 확인한다. 아래는 서울 리전 예시다.

```bash
aws bedrock list-inference-profiles \
  --region ap-northeast-2 \
  --profile litellm-lab \
  --type-equals SYSTEM_DEFINED \
  --query "inferenceProfileSummaries[?contains(inferenceProfileId, 'anthropic')].[inferenceProfileName,inferenceProfileId,status]" \
  --output table
```

출력된 Claude 프로필 중 사용할 항목의 `inferenceProfileId`를 복사한다. 목록 조회가 거부되면 `bedrock:ListInferenceProfiles` 권한 여부를 확인하거나 관리자가 알려준 모델/프로필 ID를 사용한다. 목록에 나온다는 사실만으로 추론 권한까지 보장되지는 않는다.

```bash
nano .env
```

다음 두 값을 수정한다.

```dotenv
AWS_REGION_NAME=ap-northeast-2
BEDROCK_MODEL=bedrock/여기에_실제_모델_또는_프로필_ID
```

`bedrock/` 접두어는 유지하고 한글 자리표시자는 실제 ID로 바꾼다. ARN을 사용할 경우 `bedrock/arn:aws:bedrock:...` 형식으로 지정할 수 있다. 모델 별칭 `claude-lab`은 그대로 둔다. Claude Desktop의 모델 탐색은 이름에 `claude` 또는 `anthropic`이 포함된 모델을 사용한다.

권한은 선택한 모델/프로필에 대한 `bedrock:InvokeModel`, 스트리밍에는 `bedrock:InvokeModelWithResponseStream` 등이 필요하다. Cross-Region 프로필은 대상 리전의 IAM/SCP 제약과 데이터 처리 위치도 함께 확인한다. Anthropic 모델의 최초 사용 요건이 표시되면 Bedrock 콘솔에서 완료한다.

마지막으로 WSL 프로필의 현재 자격 증명을 컨테이너용 파일에 저장한다.

```bash
python3 scripts/export_aws.py --profile litellm-lab
```

AWS CLI의 `configure export-credentials --format process`를 사용하며, 비밀값을 화면에 출력하지 않는다. `.aws.env`는 Linux 권한 `0600`으로 저장된다. 인증 파일을 만드는 것만으로 모델을 호출하거나 과금하지는 않는다.

## 4. Compose 실행

```bash
docker compose config --quiet
docker compose pull
python3 scripts/pin_images.py
docker compose up -d
docker compose ps
```

초기 태그는 공식 Quickstart의 LiteLLM `main-stable`과 PostgreSQL `16`이다. `pin_images.py`는 방금 내려받은 이미지를 digest로 고정하므로 이후 실습 재시작 시 같은 이미지를 사용한다. 버전 업그레이드 시에는 릴리스 내용을 확인하고 이미지 설정을 명시적으로 변경한다.

첫 기동은 DB 초기화·마이그레이션 때문에 시간이 걸릴 수 있다.

```bash
docker compose logs --tail=100 litellm
curl --fail --silent --show-error http://localhost:4000/health/readiness
docker compose exec litellm python -c "from importlib.metadata import version; print(version('litellm'))"
```

- `postgres`가 healthy이고 `litellm`이 실행 상태인지 확인한다.
- readiness는 DB 연결을 포함한 준비 상태를 확인한다. 여기서 성공해도 AWS 인증이나 모델 호출 성공까지 확인한 것은 아니다.
- Claude Desktop 자동 모델 탐색에는 공식 문서 기준 **LiteLLM 1.98.0 이상**이 필요하다. 낮은 버전이라면 해당 기능을 지원하는 공식 릴리스로 업데이트한다.
- 모델 전체를 호출하는 `/health`는 실제 추론 비용이 발생할 수 있어 이 실습의 반복 확인에는 사용하지 않는다.

## 5. Admin UI와 실습용 Virtual Key

**Windows 브라우저**에서 <http://localhost:4000/ui>에 접속한다.

| 로그인 항목 | 입력값 |
| --- | --- |
| Username | `admin` |
| Password | `.env`의 `UI_PASSWORD` 값 |

`Virtual Keys → Create New Key`에서 다음처럼 만든다. 버튼 명칭은 버전에 따라 조금 다를 수 있다.

- 이름/별칭: `desktop-lab`
- 허용 모델: `claude-lab`
- 예산: 예를 들어 `$5`, 갱신 기간 `30d` — 학습용 값이며 필요에 맞게 선택

생성된 Virtual Key를 보관한다. 이 키를 Python 테스트와 Claude Desktop에 넣는다. LiteLLM 예산 제한은 AWS 계정 전체의 과금 상한이 아니며, 동시 요청·집계 시점에 따라 정확한 달러 단위 차단을 보장하는 장치로 간주하지 않는다.

| 비밀값 | 사용하는 곳 |
| --- | --- |
| AWS 자격 증명 | LiteLLM → Bedrock 인증 |
| `LITELLM_MASTER_KEY` | LiteLLM 관리 API, 관리자용 |
| Virtual Key | Desktop/Python → LiteLLM 인증 |
| `UI_PASSWORD` | Admin UI 로그인 |
| `POSTGRES_PASSWORD` | LiteLLM → DB 연결 |
| `LITELLM_SALT_KEY` | LiteLLM의 DB 내 민감한 설정 암호화 |

## 6. Desktop 연결 전 API 테스트

모델 목록만 확인한다. Virtual Key 입력은 화면에 보이지 않는다.

```bash
python3 scripts/test_gateway.py
```

`접근 가능한 모델: claude-lab`과 성공 메시지가 나와야 한다. 다음 명령은 **Bedrock에 짧은 모델 요청 한 건을 보내므로 API 비용이 발생한다.**

```bash
python3 scripts/test_gateway.py --invoke
```

짧은 한국어 응답과 사용량이 출력되면 `Python → LiteLLM → Bedrock → LiteLLM → Python` 호출이 성공한 것이다. 이 스크립트도 LiteLLM을 사용하는 작은 Python 클라이언트 예제이므로 이후 프롬프트·응답 처리를 바꾸며 실습할 수 있다.

## 7. Windows Claude Desktop 연결

1. Claude Desktop의 **Help → Troubleshooting → Enable Developer Mode**를 선택한다.
2. **Developer → Configure Third-Party Inference**를 연다.
3. 다음 값을 입력하고 **Apply Changes**를 누른다.

| 항목 | 값 |
| --- | --- |
| Inference provider | `Gateway` |
| Gateway base URL | `http://localhost:4000` |
| Credential kind | 정적 API key 방식, 해당 선택 항목이 있는 경우 |
| Gateway API key | 5단계에서 만든 Virtual Key |
| Gateway auth scheme | `bearer` |

**Base URL 끝에 `/v1`을 붙이지 않는다.** `.env`에서 포트를 바꿨다면 URL도 같은 포트로 바꾼다.

4. Claude Desktop을 완전히 종료하고 다시 실행한다.
5. 새 채팅에서 `claude-lab`을 선택해 짧은 메시지를 보낸다.
6. LiteLLM Admin UI의 **Logs 또는 Usage**에서 해당 요청과 Virtual Key 사용 내역을 확인한다.

이제 모델 목록은 `GET /v1/models`, 채팅은 `POST /v1/messages`로 LiteLLM에 전달된다. 첫 실습은 일반 Chat에서 진행한다. Cowork의 도구 연결이나 MCP는 별도 단계로 확장한다.

메뉴가 없다면 Desktop 업데이트 및 해당 버전·배포 환경의 third-party inference 지원 여부를 먼저 확인한다. `claude_desktop_config.json`의 MCP 설정에 URL을 넣는 것은 이 모델 게이트웨이 설정을 대체하지 않는다.

## 8. 자주 만나는 문제

| 증상 | 확인할 내용 |
| --- | --- |
| Docker Server 접속 실패 | Docker Desktop 실행 여부, WSL Integration, Linux 컨테이너 모드 |
| `4000` 포트 사용 중 | `.env`의 `LITELLM_PORT`를 변경하고 `docker compose up -d`; Desktop URL도 변경 |
| WSL에서는 접속되고 Windows에서는 안 됨 | Docker Desktop의 포트 게시 및 방화벽 확인. `http://127.0.0.1:4000`도 시도. 바로 LAN 전체 공개로 바꾸지 않기 |
| PostgreSQL unhealthy | `docker compose logs --tail=100 postgres`; 기존 볼륨이 있는데 비밀번호만 바뀌었는지 확인 |
| LiteLLM이 반복 재시작 | `docker compose logs --tail=100 litellm`; `.env`, config, DB 연결 오류 확인 |
| HTTP 401 | 잘못된 Virtual Key, 키 만료, 공백 포함 여부 |
| HTTP 403 / AccessDenied | 키의 허용 모델, IAM/SCP, 모델 최초 사용 요건; Bedrock 권한 오류는 다른 HTTP 코드로 감싸질 수도 있음 |
| NoCredentials / ExpiredToken / InvalidClientToken | WSL 프로필 확인 후 `.aws.env` 다시 생성, LiteLLM 컨테이너 재생성 |
| 모델 ID·리전·on-demand 관련 오류 | 해당 리전에서 지원하는 모델/추론 프로필인지 확인. 프로필이 필요한 모델은 foundation model ID 대신 프로필 사용 |
| Desktop 모델 목록이 비어 있음 | LiteLLM 버전, `claude-lab` 별칭, Virtual Key의 모델 권한, base URL에서 `/v1` 제거 확인 |
| CLI 모델 요청은 성공하나 Desktop 오류 | 최신 Desktop 설정, 실제 Desktop 요청의 로그, 스트리밍 호출 권한 확인 |

SSO/임시 자격 증명은 만료된다. 이 패키지는 로그인 프로필을 자동 갱신하는 서비스가 아니라 **내보낸 자격 증명의 스냅샷**을 컨테이너에 전달한다. 만료되면:

```bash
aws sso login --profile litellm-lab
python3 scripts/export_aws.py --profile litellm-lab
docker compose up -d --force-recreate litellm
```

SSO를 쓰지 않는 프로필은 그 인증 방식에 맞게 갱신한다. `docker compose restart`만으로는 변경된 환경변수가 반영되지 않는다.

## 9. 종료·재개

```bash
# 일시 정지 — DB와 컨테이너 유지
docker compose stop

# 다시 시작
docker compose up -d

# 컨테이너와 네트워크 정리 — DB 볼륨은 유지
docker compose down
```

`docker compose down -v`는 DB 볼륨까지 삭제하므로 키·사용량 등 실습 데이터를 지우고 처음부터 시작할 때만 사용한다. 재개 시 임시 AWS 자격 증명의 유효기간도 확인한다.

이후 실습은 Python 요청 코드 수정 → Virtual Key별 모델·예산 제한 → 로깅/콜백 추가 → EC2 이전 순서로 확장하면 된다. EC2에서는 같은 컨테이너 구성과 코드를 활용할 수 있지만, AWS 인증은 인스턴스 역할로 바꾸고 외부 접속·TLS·DB 저장/백업 설정을 배포 환경에 맞춰 조정한다.

## 공식 문서와 검증 범위

작성 기준: 2026-10-14. 공식 문서의 현재 설정을 기준으로 구성했다.

- [Docker Desktop WSL2](https://docs.docker.com/desktop/features/wsl/)
- [LiteLLM Docker Quickstart](https://docs.litellm.ai/docs/proxy/docker_quick_start)
- [공식 Compose 참고 파일](https://github.com/BerriAI/litellm/blob/main/docker/docker-compose.quickstart.yml)
- [LiteLLM Bedrock 설정](https://docs.litellm.ai/docs/providers/bedrock)
- [LiteLLM 구성 파일](https://docs.litellm.ai/docs/proxy/configs)
- [LiteLLM Admin UI](https://docs.litellm.ai/docs/proxy/ui)
- [LiteLLM 상태 확인](https://docs.litellm.ai/docs/proxy/health)
- [Claude Desktop 연결](https://docs.litellm.ai/docs/proxy/client_setup/claude_desktop)
- [Claude Desktop 모델 탐색·버전 요건](https://docs.litellm.ai/docs/tutorials/claude_desktop_cowork)
- [AWS CLI 자격 증명 내보내기](https://docs.aws.amazon.com/cli/latest/reference/configure/export-credentials.html)
- [AWS CLI SSO 설정](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html)
- [Bedrock inference profile 조회](https://docs.aws.amazon.com/cli/latest/reference/bedrock/list-inference-profiles.html)

패키지의 YAML·Python 문법 및 보조 스크립트는 로컬 정적 검사와 모의 응답으로 검증했다. 비밀값의 화면 출력 방지, 기존 설정 유지, 이미지 digest 고정, 모델 목록 조회 및 명시적인 추론 요청을 확인했다. 작성 환경에는 Docker 데몬과 사용자의 AWS 자격 증명이 없으므로 실제 컨테이너 기동·Bedrock 호출·Windows Desktop 연결은 위 절차로 사용자 PC에서 확인해야 한다.
