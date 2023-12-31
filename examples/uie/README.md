## UIE

### 数据标注

我们推荐使用数据标注平台 `doccano` 进行数据标注，本示例也打通了从标注到训练的通道，即 `doccano` 导出数据后可通过 `doccano.py` 脚本轻松将数据转换为输入模型时需要的形式，实现无缝衔接。

标注完成后，使用下面命令将数据进行处理

```bash
python doccano.py \
     --doccano_file datasets/DuIE/doccano_ext.json \
    --save_dir datasets/DuIE 
```

参数说明：

+ `doccano_file`: 从 `doccano` 导出的数据标注文件


+ `save_dir`: 训练数据的保存目录，默认存储在 `data` 目录下


+ `negative_ratio`: 最大负例比例，该参数只对抽取类型任务有效，适当构造负例可提升模型效果。负例数量和实际的标签数量有关，最大负例数量 = `negative_ratio` * 正例数量。该参数只对训练集有效，默认为 `5`。为了保证评估指标的准确性，验证集和测试集默认构造全负例


+ `splits`: 划分数据集时训练集、验证集所占的比例。默认为 `[0.8, 0.1, 0.1]` 表示按照 `8:1:1` 的比例将数据划分为训练集、验证集和测试集


+ `task_type`: 选择任务类型，可选有抽取和分类两种类型的任务


+ `options`: 指定分类任务的类别标签，该参数只对分类类型任务有效。默认为 `["正向", "负向"]`


+ `prompt_prefix`: 声明分类任务的 `prompt` 前缀信息，该参数只对分类类型任务有效。默认为 "情感倾向"


+ `is_shuffle`: 是否对数据集进行随机打散，默认为 `True`


+ `seed`: 随机种子，默认为 `1000`


+ `separator`: 实体类别/评价维度与分类标签的分隔符，该参数只对实体/评价维度级分类任务有效。默认为 `"##"`


+ `schema_lang`: 选择 `schema` 的语言，可选有 `ch` 和 `en`。默认为 `ch`，英文数据集请选择 `en`


处理之后的数据示例如下

```json
{
  "content": "王国维，字静安，又字伯隅，号观堂",
  "result_list": [
    {
      "text": "观堂",
      "start": 14,
      "end": 16
    }
  ],
  "prompt": "王国维的号"
}
```

### 模型微调

```shell
export TASK_NAME=uie
export MODEL_NAME_OR_PATH=xusenlin/uie-base
export OUTPUT_DIR=outputs
export DATA_DIR=datasets/12315

python train.py \
    --task_name $TASK_NAME \
    --model_name_or_path $MODEL_NAME_OR_PATH \
    --dataset_name $DATA_DIR \
    --train_file train.json \
    --validation_file dev.json \
    --cache_dir $DATA_DIR/$TASK_NAME \
    --preprocessing_num_workers 16 \
    --num_train_epochs 20 \
    --per_device_train_batch_size 4 \
    --per_device_eval_batch_size 4 \
    --output_dir $OUTPUT_DIR/$TASK_NAME
```

### 模型结果（DUIE 100条数据）

|         DA method         | backbone model |   val_f1   | val_precision | val_recall | 
|:-------------------------:|:--------------:|:----------:|:-------------:|:----------:|
|         Baseline          |    uie_base    |   83.33%   |    78.43%     |   88.89%   | 
|         Swap SPO          |    uie_base    | 84.55% (↑) |  78.85%* (↑)  | 91.11% (↑) | 
|         Auto Neg          |    uie_base    |            |               |            | 
|      Mask Then Fill       |    uie_base    |            |               |            | 
| Mask Then Fill & Auto Neg |    uie_base    |            |               |            | 
