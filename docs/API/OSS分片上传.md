---
title: "对象存储"
source: "https://help.aliyun.com/zh/oss/user-guide/multipart-upload?spm=a2c4g.11186623.help-menu-31815.d_0_3_1_1.43e970aeMV138f&scm=20140722.H_31850._.OR_help-T_cn~zh-V_1#31487456224qh"
author:
published:
created: 2026-07-31
description: "阿里云对象存储OSS（Object Storage Service）是一款海量、安全、低成本、高可靠的云存储服务，可提供99.9999999999%（12个9）的数据持久性，99.995%的数据可用性。多种存储类型供选择，全面优化存储成本。"
tags:
  - "clippings"
---
大文件上传面临网络中断风险和传输时间过长的挑战。分片上传通过将文件分割为多个小分片并发传输，提供断点续传能力和传输性能优化，有效应对网络不稳定环境下的文件传输需求。

## 工作原理

分片上传将大文件分割为多个小分片进行独立处理，各分片独立传输和校验，单个分片失败时仅需重传该分片，避免重新上传整个文件。分片上传使用Upload ID作为任务标识符，确保所有分片正确归属于同一个上传任务。核心流程分为三个步骤：

1. **初始化上传任务** ：调用InitiateMultipartUpload接口创建分片上传任务，获取唯一的Upload ID作为后续操作的标识符。
2. **上传文件分片数据** ：将文件切分为多个分片（Part）并发上传，每个分片大小在100KB到5GB之间，支持断点续传。
3. **合并分片完成上传** ：调用CompleteMultipartUpload接口将所有分片按序号合并为完整的对象文件。
![image](https://help-static-aliyun-doc.aliyuncs.com/assets/img/zh-CN/4016943871/CAEQYxiBgMCtxcXpzxkiIDE1ZmJkYjAyZmFiZDQ1YjFiMTVmZDI3OGQ2OTJjN2Ix5798772_20251019104257.734.svg)

## 实现大文件分片上传

根据应用场景和技术要求，可选择图形化工具、命令行工具或SDK来实现分片上传功能。

**说明**

- OSS控制台暂不支持分片上传操作。
- 支持上传加密的压缩文件，但不支持上传目录。

### 通过工具自动分片

对于日常开发、测试、运维或手动上传场景，推荐使用图形化或命令行工具，工具会自动处理分片逻辑，操作便捷。

- **图形化管理工具ossbrowser**
	使用 [图形化管理工具ossbrowser 2.0](https://help.aliyun.com/zh/oss/developer-reference/ossbrowser-2-0-overview/) 上传文件时，默认启用分片上传机制，并提供可视化的上传进度和状态监控。
- **命令行工具ossutil**
	使用 [命令行工具ossutil 2.0](https://help.aliyun.com/zh/oss/developer-reference/ossutil-overview/) 的 [cp](https://help.aliyun.com/zh/oss/developer-reference/cp-upload-file) 命令上传文件时，工具会自动对超过100MiB的文件启用分片上传，提高大文件上传的成功率和传输效率。如需手动控制分片上传过程，可组合使用 [initiate-multipart-upload](https://help.aliyun.com/zh/oss/developer-reference/initiate-multipart-upload) 、 [upload-part](https://help.aliyun.com/zh/oss/developer-reference/upload-part) 和 [complete-multipart-upload](https://help.aliyun.com/zh/oss/developer-reference/complete-multipart-upload) 命令。
	```shell
	ossutil cp example.zip oss://example-bucket
	```

### 通过SDK编程实现分片

各语言SDK提供完整的分片上传接口封装，支持自定义分片大小、并发控制和错误处理。以下为常见语言的SDK分片上传示例，更多语言的使用示例请参见 [SDK参考](https://help.aliyun.com/zh/oss/developer-reference/sdk-code-samples/) 中对应语言的示例代码。

> 运行代码前需安装对应语言的SDK并配置访问凭证环境变量，使用RAM用户或RAM角色时还需参考进行接口授权。

Java SDK V2

Java SDK V1

Python SDK V2

Python SDK V1

Go SDK V2

Go SDK V1

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# OSS Python SDK V2 分片上传示例
# 实现大文件的分片上传功能

import alibabacloud_oss_v2 as oss
import os

def main():
    # 从环境变量获取访问凭证
    credentials_provider = oss.credentials.EnvironmentVariableCredentialsProvider()

    # 加载SDK的默认配置
    config = oss.config.load_default()
    config.credentials_provider = credentials_provider

    # 设置OSS地域和Endpoint
    config.region = "cn-hangzhou"
    config.endpoint = "oss-cn-hangzhou.aliyuncs.com"

    # 初始化OSS客户端
    client = oss.Client(config)

    # 配置Bucket和文件信息
    bucket = "example-bucket"
    key = "dest.jpg"
    file_path = "dest.jpg"

    try:
        # 步骤1：初始化分片上传
        initiate_result = client.initiate_multipart_upload(
            oss.InitiateMultipartUploadRequest(
                bucket=bucket,
                key=key
            ))

        upload_id = initiate_result.upload_id
        print(f"初始化分片上传成功，状态码:{initiate_result.status_code}, "
              f"请求ID:{initiate_result.request_id}, 上传ID:{upload_id}")

        # 步骤2：上传分片
        file_size = os.path.getsize(file_path)
        part_size = 100 * 1024  # 每个分片100KB
        part_number = 1
        upload_parts = []
        offset = 0

        with open(file_path, 'rb') as f:
            while offset < file_size:
                # 计算当前分片大小
                current_part_size = min(part_size, file_size - offset)
                
                # 读取分片数据
                f.seek(offset)
                part_data = f.read(current_part_size)

                # 上传分片
                part_result = client.upload_part(
                    oss.UploadPartRequest(
                        bucket=bucket,
                        key=key,
                        upload_id=upload_id,
                        part_number=part_number,
                        body=part_data
                    ))

                print(f"状态码: {part_result.status_code}, 请求ID: {part_result.request_id}, "
                      f"分片号: {part_number}, ETag: {part_result.etag}")

                # 记录已上传的分片信息
                upload_parts.append(oss.UploadPart(
                    part_number=part_number,
                    etag=part_result.etag
                ))

                offset += current_part_size
                part_number += 1

        # 步骤3：完成分片上传
        upload_parts.sort(key=lambda p: p.part_number)

        complete_result = client.complete_multipart_upload(
            oss.CompleteMultipartUploadRequest(
                bucket=bucket,
                key=key,
                upload_id=upload_id,
                complete_multipart_upload=oss.CompleteMultipartUpload(
                    parts=upload_parts
                )
            ))

        print(f"完成分片上传，状态码:{complete_result.status_code}, "
              f"请求ID:{complete_result.request_id}, "
              f"Bucket:{complete_result.bucket}, "
              f"Key:{complete_result.key}, "
              f"位置:{complete_result.location}, "
              f"ETag:{complete_result.etag}")

    except Exception as e:
        print(f"错误: {e}")
        raise

if __name__ == "__main__":
    main()
```

## 清理碎片文件

分片上传过程意外中断且未调用AbortMultipartUpload接口时，已上传的分片会作为碎片文件保留在Bucket中并 **持续产生存储费用** 。及时清理这些碎片文件可避免不必要的存储成本。

#### 通过控制台

1. 前往 [Bucket列表](https://oss.console.aliyun.com/bucket) ，单击目标Bucket。
2. 在 **文件列表** 单击 **碎片管理** ，查看并删除碎片文件。

#### 通过生命周期规则

配置生命周期规则可实现对过期碎片的自动清理，减少手动维护工作量并防止遗漏。具体操作参见 [通过生命周期规则清理过期碎片](https://help.aliyun.com/zh/oss/user-guide/configuration-examples#section-fxr-uqg-cw0) 。

#### 通过工具

- **图形化管理工具ossbrowser**
	在Bucket的文件列表页面单击 **文件碎片** ，查看并删除碎片文件。
- **命令行工具ossutil**
	使用 [abort-multipart-upload](https://help.aliyun.com/zh/oss/developer-reference/abort-multipart-upload) 命令取消分片上传任务并删除对应的分片数据。命令示例如下：
	```shell
	ossutil api abort-multipart-upload --bucket example-bucket --key dest.jpg --upload-id D9F4****************************
	```

#### 通过SDK

通过调用AbortMultipartUpload接口取消分片上传任务并删除对应的分片数据。以下为常见语言的SDK取消分片上传任务代码示例，更多语言的使用示例请参见 [SDK参考](https://help.aliyun.com/zh/oss/developer-reference/sdk-code-samples/) 中对应语言的示例代码。

> 运行代码前需安装对应语言的SDK并配置访问凭证环境变量，使用RAM用户或RAM角色时还需参考进行接口授权。

Java SDK V2

Java SDK V1

Python SDK V2

Python SDK V1

Go SDK V2

Go SDK V1

```java
import com.aliyun.sdk.service.oss2.OSSClient;
import com.aliyun.sdk.service.oss2.credentials.CredentialsProvider;
import com.aliyun.sdk.service.oss2.credentials.StaticCredentialsProvider;
import com.aliyun.sdk.service.oss2.models.AbortMultipartUploadRequest;
import com.aliyun.sdk.service.oss2.models.AbortMultipartUploadResult;

/**
 * OSS取消分片上传示例
 * 演示如何取消一个分片上传任务
 */
public class AbortMultipartUpload {

    public static void main(String[] args) {
        // 从环境变量获取访问凭证
        String accessKeyId = System.getenv("OSS_ACCESS_KEY_ID");
        String accessKeySecret = System.getenv("OSS_ACCESS_KEY_SECRET");

        // 设置OSS地域和Endpoint
        String region = "cn-hangzhou";
        String endpoint = "oss-cn-hangzhou.aliyuncs.com";

        // 配置Bucket和文件信息
        String bucket = "example-bucket";
        String key = "dest.jpg";
        String uploadId = "D9F4****************************";

        // 创建凭证提供者
        CredentialsProvider provider = new StaticCredentialsProvider(accessKeyId, accessKeySecret);

        // 初始化OSS客户端
        OSSClient client = OSSClient.newBuilder()
                .credentialsProvider(provider)
                .region(region)
                .endpoint(endpoint)
                .build();

        try {
            // 取消分片上传
            AbortMultipartUploadResult result = client.abortMultipartUpload(
                    AbortMultipartUploadRequest.newBuilder()
                            .bucket(bucket)
                            .key(key)
                            .uploadId(uploadId)
                            .build());

            System.out.printf("取消分片上传成功，状态码: %d, 请求ID: %s\n",
                    result.statusCode(), result.requestId());

        } catch (Exception e) {
            System.out.printf("错误: %s\n", e.getMessage());
            e.printStackTrace();
        } finally {
            // 关闭客户端连接
            try {
                client.close();
            } catch (Exception e) {
                e.printStackTrace();
            }
        }
    }
}
```

```java
import com.aliyun.oss.*;
import com.aliyun.oss.common.auth.*;
import com.aliyun.oss.common.comm.SignVersion;
import com.aliyun.oss.model.*;

/**
 * OSS取消分片上传示例（V1 SDK）
 * 演示如何取消一个分片上传任务
 */
public class AbortMultipartUpload {

    public static void main(String[] args) {
        // 从环境变量获取访问凭证
        String accessKeyId = System.getenv("OSS_ACCESS_KEY_ID");
        String accessKeySecret = System.getenv("OSS_ACCESS_KEY_SECRET");

        // 设置OSS地域和Endpoint
        String region = "cn-hangzhou";
        String endpoint = "oss-cn-hangzhou.aliyuncs.com";

        // 配置Bucket和文件信息
        String bucketName = "example-bucket";
        String objectName = "dest.jpg";
        String uploadId = "D9F4****************************";

        // 创建凭证提供者
        DefaultCredentialProvider provider = new DefaultCredentialProvider(accessKeyId, accessKeySecret);

        // 配置客户端参数
        ClientBuilderConfiguration clientBuilderConfiguration = new ClientBuilderConfiguration();
        clientBuilderConfiguration.setSignatureVersion(SignVersion.V4);

        // 初始化OSS客户端
        OSS ossClient = OSSClientBuilder.create()
                .credentialsProvider(provider)
                .clientConfiguration(clientBuilderConfiguration)
                .region(region)
                .endpoint(endpoint)
                .build();

        try {
            // 取消分片上传
            AbortMultipartUploadRequest abortMultipartUploadRequest =
                    new AbortMultipartUploadRequest(bucketName, objectName, uploadId);
            ossClient.abortMultipartUpload(abortMultipartUploadRequest);

            System.out.printf("取消分片上传成功，上传ID: %s\n", uploadId);

        } catch (Exception e) {
            System.out.printf("错误: %s\n", e.getMessage());
            e.printStackTrace();
        } finally {
            // 关闭客户端连接
            ossClient.shutdown();
        }
    }
}
```

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# OSS Python SDK V2 取消分片上传示例
# 取消分片上传任务并删除已上传的分片

import alibabacloud_oss_v2 as oss

def main():
    # 从环境变量获取访问凭证
    credentials_provider = oss.credentials.EnvironmentVariableCredentialsProvider()

    # 加载SDK的默认配置
    config = oss.config.load_default()
    config.credentials_provider = credentials_provider

    # 设置OSS地域和Endpoint
    config.region = "cn-hangzhou"
    config.endpoint = "oss-cn-hangzhou.aliyuncs.com"

    # 初始化OSS客户端
    client = oss.Client(config)

    # 配置Bucket和文件信息
    bucket = "example-bucket"
    key = "dest.jpg"
    upload_id = "D9F4****************************"

    # 取消分片上传
    result = client.abort_multipart_upload(
        oss.AbortMultipartUploadRequest(
            bucket=bucket,
            key=key,
            upload_id=upload_id
        ))

    print(f"取消分片上传成功，状态码: {result.status_code}, 请求ID: {result.request_id}")

if __name__ == "__main__":
    main()
```

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# OSS Python SDK V1 取消分片上传示例

import oss2
from oss2.credentials import EnvironmentVariableCredentialsProvider

def main():
    # 从环境变量中获取访问凭证
    auth = oss2.ProviderAuthV4(EnvironmentVariableCredentialsProvider())
    
    # 设置OSS地域和Endpoint
    region = "cn-hangzhou"
    endpoint = "https://oss-cn-hangzhou.aliyuncs.com"
    
    # 配置Bucket和文件信息
    bucket_name = "example-bucket"
    key = "dest.jpg"
    upload_id = "D9F4****************************"
    
    # 初始化OSS客户端
    bucket = oss2.Bucket(auth, endpoint, bucket_name, region=region)
    
    # 取消分片上传
    bucket.abort_multipart_upload(key, upload_id)
    
    print(f"取消分片上传成功，上传ID: {upload_id}")

if __name__ == "__main__":
    main()
```

```
package main

// OSS Go SDK V2 取消分片上传示例

import (
    "context"
    "fmt"

    "github.com/aliyun/alibabacloud-oss-go-sdk-v2/oss"
    "github.com/aliyun/alibabacloud-oss-go-sdk-v2/oss/credentials"
)

func main() {
    // 从环境变量获取访问凭证
    // 配置OSS客户端，设置凭证提供者和Endpoint
    config := oss.LoadDefaultConfig().
        WithCredentialsProvider(credentials.NewEnvironmentVariableCredentialsProvider()).
        WithRegion("cn-hangzhou").
        WithEndpoint("oss-cn-hangzhou.aliyuncs.com")

    // 初始化OSS客户端
    client := oss.NewClient(config)

    // 配置Bucket和文件信息
    bucket := "example-bucket"
    key := "dest.jpg"
    uploadId := "D9F4****************************"

    // 取消分片上传
    client.AbortMultipartUpload(context.TODO(), &oss.AbortMultipartUploadRequest{
        Bucket:   oss.Ptr(bucket),
        Key:      oss.Ptr(key),
        UploadId: oss.Ptr(uploadId),
    })

    fmt.Printf("取消分片上传成功，上传ID: %s\n", uploadId)
}
```

```
package main

// OSS Go SDK V1 取消分片上传示例

import (
    "fmt"

    "github.com/aliyun/aliyun-oss-go-sdk/oss"
)

func main() {
    // 从环境变量获取访问凭证
    provider, _ := oss.NewEnvironmentVariableCredentialsProvider()

    // 创建OSS客户端实例
    client, _ := oss.New(
        "oss-cn-hangzhou.aliyuncs.com",
        "",
        "",
        oss.SetCredentialsProvider(&provider),
        oss.AuthVersion(oss.AuthV4),
        oss.Region("cn-hangzhou"),
    )

    // 获取Bucket对象
    bucket, _ := client.Bucket("example-bucket")

    // 配置文件信息
    key := "dest.jpg"
    uploadId := "D9F4****************************"

    // 创建InitiateMultipartUploadResult对象
    imur := oss.InitiateMultipartUploadResult{
        UploadID: uploadId,
        Key:      key,
    }

    // 取消分片上传
    bucket.AbortMultipartUpload(imur)

    fmt.Printf("取消分片上传成功，上传ID: %s\n", uploadId)
}
```

## 应用于生产环境

#### 最佳实践

- **性能优化：提升上传速度和稳定性**
	- **合理控制并发数量** ：根据网络带宽和设备负载确定合理的并发分片数量。过多的并发连接会增加系统负载和网络拥塞，过少则无法充分利用网络资源。
		- **避免顺序前缀命名** ：上传大量文件时避免使用顺序前缀（如时间戳开头），防止请求集中在特定分区造成热点问题，影响整体上传性能。详见 [OSS性能最佳实践](https://help.aliyun.com/zh/oss/user-guide/oss-performance-best-practices/#concept-xtt-pln-vdb) 。
- **可靠性保障：实现断点续传**
	分片上传任务无过期时间限制，支持暂停和恢复操作。利用Upload ID作为任务标识符，当单个分片上传失败时，仅需重传该分片，避免从头开始上传整个文件，大幅提升传输效率。
- **成本优化：优化深度冷归档上传策略**
	对于需要存储到深度冷归档的大量文件，建议先上传为标准存储类型，再通过 [生命周期规则](https://help.aliyun.com/zh/oss/user-guide/lifecycle-rules-based-on-the-last-modified-time#concept-y2g-szy-5db) 自动转换存储类型，避免直接上传产生高额的PUT请求费用。

#### 风险防范

- **数据安全：防止文件覆盖**
	在上传请求header中设置 `x-oss-forbid-overwrite` 参数为 `true` ，防止覆盖同名文件造成数据丢失。也可开启 [版本控制](https://help.aliyun.com/zh/oss/user-guide/overview-78/#concept-jdg-4rx-bgb) 功能保留历史版本。

## 配额与限制

<table><tbody><tr><td rowspan="1" colspan="1"><p><b>限制项</b></p></td><td rowspan="1" colspan="1"><p><b>说明</b></p></td></tr><tr><td rowspan="1" colspan="1"><p>单个文件的大小</p></td><td rowspan="1" colspan="1"><p>不超过48.8TB</p></td></tr><tr><td rowspan="1" colspan="1"><p>分片数量</p></td><td rowspan="1" colspan="1"><p>1~10,000个</p></td></tr><tr><td rowspan="1" colspan="1"><p>单个分片大小</p></td><td rowspan="1" colspan="1"><p>最小值为100KB，最大值为5GB。最后一个分片的大小允许小于100KB。</p></td></tr><tr><td rowspan="1" colspan="1"><p>单次ListParts请求返回的分片最大数量</p></td><td rowspan="1" colspan="1"><p>1,000个</p></td></tr><tr><td rowspan="1" colspan="1"><p>单次ListMultipartUploads请求返回的分片上传事件最大数量</p></td><td rowspan="1" colspan="1"><p>1,000个</p></td></tr></tbody></table>

## 计费说明

分片上传过程中不同接口产生相应的计费项目如下表所示。详细的计费说明请参见 [请求费用](https://help.aliyun.com/zh/oss/api-operation-calling-fees) 和 [存储费用](https://help.aliyun.com/zh/oss/storage-fees) 。

<table><tbody><tr><td rowspan="1" colspan="1"><p><b>API</b></p></td><td rowspan="1" colspan="1"><p><b>计费项</b></p></td><td rowspan="1" colspan="1"><p><b>说明</b></p></td></tr><tr><td rowspan="1" colspan="1"><p><b>InitiateMultipartUpload</b></p></td><td rowspan="1" colspan="1"><p>PUT 类型请求</p></td><td rowspan="1" colspan="1"><p>根据成功的请求次数计算请求费用。</p></td></tr><tr><td rowspan="2" colspan="1"><p><b>UploadPart</b></p></td><td rowspan="1" colspan="1"><p>PUT 类型请求</p></td><td rowspan="1" colspan="1"><p>根据成功的请求次数计算请求费用。</p></td></tr><tr><td rowspan="1" colspan="1"><p>存储费用</p></td><td rowspan="1" colspan="1"><p>根据分片的存储类型（与对象文件类型一致）、实际大小和存储时长收取存储费用。无最小计量单位限制，被删除或合并为完整的对象文件后停止计费。</p></td></tr><tr><td rowspan="1" colspan="1"><p><b>UploadPartCopy</b></p></td><td rowspan="1" colspan="1"><p>PUT 类型请求</p></td><td rowspan="1" colspan="1"><p>根据成功的请求次数计算请求费用。</p></td></tr><tr><td rowspan="2" colspan="1"><p><b>CompleteMultipartUpload</b></p></td><td rowspan="1" colspan="1"><p>PUT 类型请求</p></td><td rowspan="1" colspan="1"><p>根据成功的请求次数计算请求费用。</p></td></tr><tr><td rowspan="1" colspan="1"><p>存储费用</p></td><td rowspan="1" colspan="1"><p>根据对象文件的存储类型、大小和时长收取存储费用。</p></td></tr><tr><td rowspan="1" colspan="1"><p><b>AbortMultipartUpload</b></p></td><td rowspan="1" colspan="1"><p>PUT 类型请求</p></td><td rowspan="1" colspan="1"><p>根据成功的请求次数计算请求费用。</p><p><strong>重要</strong></p><div><ul><li><p>在中国内地各地域，通过生命周期规则删除低频访问、归档、冷归档类型碎片的PUT类请求费用高于删除标准存储类型碎片的PUT类请求费用；通过生命周期规则删除深度冷归档存储类型碎片，不收取PUT类请求费用。</p></li><li><p>在中国香港以及海外地域，通过生命周期规则删除各存储类型碎片时不收取PUT类请求费用。</p></li></ul></div></td></tr><tr><td rowspan="1" colspan="1"><p><b>ListMultipartUploads</b></p></td><td rowspan="1" colspan="1"><p>PUT 类型请求</p></td><td rowspan="1" colspan="1"><p>根据成功的请求次数计算请求费用。</p></td></tr><tr><td rowspan="1" colspan="1"><p><b>ListParts</b></p></td><td rowspan="1" colspan="1"><p>PUT 类型请求</p></td><td rowspan="1" colspan="1"><p>根据成功的请求次数计算请求费用。</p></td></tr></tbody></table>

**说明**

当您使用 `UploadPartCopy` 从已有对象拷贝数据来上传分片时，如果源对象的存储类型为低频访问、归档或冷归档，会产生数据取回费用（若源对象为归档类型且已开启归档直读，则产生归档直读费用）；此外，低频访问、归档、冷归档等存储类型存在最小存储时长和最小计量容量要求，可能产生相应的最小存储费用。

## API和权限说明

阿里云主账号默认拥有全部API的操作权限。RAM用户或RAM角色使用分片上传功能需根据具体操作的API授予相应权限。更多信息请参见 [RAM Policy概述](https://help.aliyun.com/zh/oss/ram-policy-overview/) 和 [RAM Policy常见示例](https://help.aliyun.com/zh/oss/common-examples-of-ram-policies) 。

<table><tbody><tr><td rowspan="1" colspan="1"><p><b>API</b></p></td><td rowspan="1" colspan="1"><p><b>Action</b></p></td><td rowspan="1" colspan="1"><p><b>说明</b></p></td></tr><tr><td rowspan="4" colspan="1"><p><b>InitiateMultipartUpload</b></p></td><td rowspan="1" colspan="1"><p><code>oss:PutObject</code></p></td><td rowspan="1" colspan="1"><p>初始化分片上传任务。</p></td></tr><tr><td rowspan="1" colspan="1"><p><code>oss:PutObjectTagging</code></p></td><td rowspan="1" colspan="1"><p>初始化分片上传任务时，如果通过x-oss-tagging指定对象文件的标签，则需要此操作的权限。</p></td></tr><tr><td rowspan="1" colspan="1"><p><code>kms:GenerateDataKey</code></p></td><td rowspan="2" colspan="1"><p>上传对象文件时，如果对象文件的元数据包含X-Oss-Server-Side-Encryption: KMS，则需要这两个操作的权限。</p></td></tr><tr><td rowspan="1" colspan="1"><p><code>kms:Decrypt</code></p></td></tr><tr><td rowspan="1" colspan="1"><p><b>UploadPart</b></p></td><td rowspan="1" colspan="1"><p><code>oss:PutObject</code></p></td><td rowspan="1" colspan="1"><p>上传分片。</p></td></tr><tr><td rowspan="3" colspan="1"><p><b>UploadPartCopy</b></p></td><td rowspan="1" colspan="1"><p><code>oss:GetObject</code></p></td><td rowspan="1" colspan="1"><p>从一个已存在的对象文件中拷贝数据来上传一个分片时，需要读取源对象文件的权限。</p></td></tr><tr><td rowspan="1" colspan="1"><p><code>oss:PutObject</code></p></td><td rowspan="1" colspan="1"><p>从一个已存在的对象文件中拷贝数据来上传一个分片时，需要写入目标对象文件的权限。</p></td></tr><tr><td rowspan="1" colspan="1"><p><code>oss:GetObjectVersion</code></p></td><td rowspan="1" colspan="1"><p>从一个已存在的对象文件中拷贝数据来上传一个分片时，如果通过versionId指定对象文件的版本，需要读取源对象文件的指定版本的权限。</p></td></tr><tr><td rowspan="2" colspan="1"><p><b>CompleteMultipartUpload</b></p></td><td rowspan="1" colspan="1"><p><code>oss:PutObject</code></p></td><td rowspan="1" colspan="1"><p>将分片合并为对象文件。</p></td></tr><tr><td rowspan="1" colspan="1"><p><code>oss:PutObjectTagging</code></p></td><td rowspan="1" colspan="1"><p>将分片合并为对象文件时，如果通过x-oss-tagging指定对象文件的标签，则需要此操作的权限。</p></td></tr><tr><td rowspan="1" colspan="1"><p><b>AbortMultipartUpload</b></p></td><td rowspan="1" colspan="1"><p><code>oss:AbortMultipartUpload</code></p></td><td rowspan="1" colspan="1"><p>取消分片上传事件并删除对应的分片数据。</p></td></tr><tr><td rowspan="1" colspan="1"><p><b>ListMultipartUploads</b></p></td><td rowspan="1" colspan="1"><p><code>oss:ListMultipartUploads</code></p></td><td rowspan="1" colspan="1"><p>列举所有执行中的分片上传事件，即已经初始化但尚未完成或者尚未被中止的分片上传事件。</p></td></tr><tr><td rowspan="1" colspan="1"><p><b>ListParts</b></p></td><td rowspan="1" colspan="1"><p><code>oss:ListParts</code></p></td><td rowspan="1" colspan="1"><p>列举指定Upload ID所属的所有已经上传成功的分片。</p></td></tr></tbody></table>