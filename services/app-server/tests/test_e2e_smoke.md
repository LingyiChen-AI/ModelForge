# E2E 冒烟(需 docker compose 全开 + worker 运行)
1. 启动 worker: cd services/ml-worker && celery -A worker.celery_app worker -c 1 -l info
2. 启动 app:    cd services/app-server && uvicorn app.main:app --port 8000
3. 建分类数据集并上传 CSV(text,label,>=8 行两类)
4. POST /training-jobs {dataset_version_id, base_model:"prajjwal1/bert-tiny",
   task_type:"classification", hyperparams:{epochs:1,batch_size:4}}
5. 轮询 GET /training-jobs/{id} 直到 status=succeeded
6. GET /model-versions 应出现一条,train_metrics 含 accuracy
7. MLflow UI(:5000)能看到 run 与 Registered Model
