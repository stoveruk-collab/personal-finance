# AWS Lightsail Deployment

This document describes the legacy Lightsail deployment helper kept in the repository for reference.

## Shape

- Lightsail container service for the FastAPI app
- Lightsail PostgreSQL for the application database
- App secrets supplied through environment variables

## Tags

The deployment helper applies generic cost-allocation tags:

- `Project=personal-finance`
- `Environment=prod`
- `Owner=<configured owner tag>`
- `ManagedBy=codex`
- `App=personal-finance`

## Setup

1. Copy the example environment file:

```bash
cp .env.aws.example .env.aws
```

2. Fill in the application secrets and deployment-specific values.

3. Authenticate the AWS CLI.

4. Run bootstrap:

```bash
scripts/aws-lightsail-deploy.sh bootstrap
```

5. Deploy the application:

```bash
scripts/aws-lightsail-deploy.sh deploy
```

## Notes

- This path is kept mainly as an infrastructure example.
- For a public fork, replace all placeholder values with your own cloud resources and credentials.
