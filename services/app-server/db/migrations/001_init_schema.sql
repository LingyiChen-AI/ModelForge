-- 001 init schema (auto-generated baseline from SQLAlchemy models, idempotent)

CREATE TABLE IF NOT EXISTS permissions (
	id SERIAL NOT NULL, 
	code VARCHAR NOT NULL, 
	description VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code)
);

CREATE TABLE IF NOT EXISTS roles (
	id SERIAL NOT NULL, 
	name VARCHAR NOT NULL, 
	description VARCHAR NOT NULL, 
	data_scope VARCHAR NOT NULL, 
	is_system BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS role_permissions (
	role_id INTEGER NOT NULL, 
	permission_id INTEGER NOT NULL, 
	PRIMARY KEY (role_id, permission_id), 
	FOREIGN KEY(role_id) REFERENCES roles (id), 
	FOREIGN KEY(permission_id) REFERENCES permissions (id)
);

CREATE TABLE IF NOT EXISTS users (
	id SERIAL NOT NULL, 
	name VARCHAR NOT NULL, 
	email VARCHAR NOT NULL, 
	password_hash VARCHAR NOT NULL, 
	role_id INTEGER, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email), 
	FOREIGN KEY(role_id) REFERENCES roles (id)
);

CREATE TABLE IF NOT EXISTS datasets (
	id SERIAL NOT NULL, 
	name VARCHAR NOT NULL, 
	kind VARCHAR NOT NULL, 
	task_type VARCHAR NOT NULL, 
	schema JSON NOT NULL, 
	created_by INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS dataset_versions (
	id SERIAL NOT NULL, 
	dataset_id INTEGER NOT NULL, 
	version_no INTEGER NOT NULL, 
	storage_uri VARCHAR NOT NULL, 
	row_count INTEGER NOT NULL, 
	checksum VARCHAR NOT NULL, 
	stats JSON NOT NULL, 
	note VARCHAR NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (dataset_id, version_no), 
	FOREIGN KEY(dataset_id) REFERENCES datasets (id)
);

CREATE TABLE IF NOT EXISTS training_jobs (
	id SERIAL NOT NULL, 
	name VARCHAR NOT NULL, 
	dataset_version_id INTEGER NOT NULL, 
	base_model VARCHAR NOT NULL, 
	task_type VARCHAR NOT NULL, 
	hyperparams JSON NOT NULL, 
	status VARCHAR NOT NULL, 
	celery_task_id VARCHAR, 
	mlflow_run_id VARCHAR, 
	error VARCHAR, 
	created_by INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(dataset_version_id) REFERENCES dataset_versions (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS model_versions (
	id SERIAL NOT NULL, 
	name VARCHAR NOT NULL, 
	source_training_job_id INTEGER NOT NULL, 
	mlflow_model_name VARCHAR NOT NULL, 
	mlflow_version VARCHAR NOT NULL, 
	task_type VARCHAR NOT NULL, 
	base_model VARCHAR NOT NULL, 
	train_metrics JSON NOT NULL, 
	stage VARCHAR NOT NULL, 
	artifact_uri VARCHAR, 
	created_by INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(source_training_job_id) REFERENCES training_jobs (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS deployments (
	id SERIAL NOT NULL, 
	model_version_id INTEGER NOT NULL, 
	endpoint VARCHAR, 
	mode VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	replicas INTEGER NOT NULL, 
	config JSON NOT NULL, 
	error VARCHAR, 
	created_by INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(model_version_id) REFERENCES model_versions (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS eval_runs (
	id SERIAL NOT NULL, 
	model_version_id INTEGER NOT NULL, 
	dataset_version_id INTEGER NOT NULL, 
	metric_config JSON NOT NULL, 
	status VARCHAR NOT NULL, 
	celery_task_id VARCHAR, 
	results JSON NOT NULL, 
	per_sample_uri VARCHAR, 
	error VARCHAR, 
	created_by INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(model_version_id) REFERENCES model_versions (id), 
	FOREIGN KEY(dataset_version_id) REFERENCES dataset_versions (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);
