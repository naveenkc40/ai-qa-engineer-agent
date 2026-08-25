def publishEvidence() {
    junit(
        testResults: 'test-results/junit.xml,docker-test-results/junit.xml',
        allowEmptyResults: true
    )
    archiveArtifacts(
        artifacts: 'coverage.xml,test-results/**,docker-test-results/**,execution-evidence/**',
        allowEmptyArchive: true
    )
}

pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '30', artifactNumToKeepStr: '10'))
    }

    environment {
        IMAGE_TAG = "ai-qe-agent:${BUILD_NUMBER}"
        EVIDENCE_PUBLISHED = 'false'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Environment Setup') {
            steps {
                sh '''
                    python3 -m venv .venv
                    .venv/bin/python -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ is required"'
                    .venv/bin/pip install --upgrade pip
                    .venv/bin/pip install -r requirements.txt
                    .venv/bin/pip install -r requirements-dev.txt
                '''
            }
        }

        stage('Static Analysis') {
            steps {
                sh '.venv/bin/ruff check .'
            }
        }

        stage('Deterministic Tests') {
            steps {
                sh '''
                    mkdir -p test-results
                    .venv/bin/python -m pytest \
                        --junitxml=test-results/junit.xml \
                        --cov=agents \
                        --cov=tools \
                        --cov-report=term-missing \
                        --cov-report=xml:coverage.xml
                '''
            }
        }

        stage('Docker Build') {
            steps {
                sh 'docker build --tag "${IMAGE_TAG}" --file Dockerfile .'
            }
        }

        stage('Container Validation') {
            steps {
                sh '''
                    mkdir -p docker-test-results
                    docker run --rm "${IMAGE_TAG}" ruff check .
                    docker run --rm \
                        --mount "type=bind,source=${WORKSPACE}/docker-test-results,target=/test-results" \
                        "${IMAGE_TAG}" \
                        python -m pytest \
                            --junitxml=/test-results/junit.xml \
                            --cov=agents \
                            --cov=tools \
                            --cov-report=term-missing \
                            --cov-report=xml:/test-results/coverage.xml
                '''
            }
        }

        stage('Evidence Publishing') {
            steps {
                script {
                    publishEvidence()
                    env.EVIDENCE_PUBLISHED = 'true'
                }
            }
        }
    }

    post {
        always {
            sh 'rm -rf .venv || true'
            sh 'docker image rm "${IMAGE_TAG}" || true'
            script {
                if (env.EVIDENCE_PUBLISHED != 'true') {
                    publishEvidence()
                }
            }
        }
    }
}
