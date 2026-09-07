---
title: "对象存储"
source: "https://help.aliyun.com/zh/oss/user-guide/simple-upload?spm=a2c4g.11186623.help-menu-31815.d_0_3_1_0.58457dc0lcb6aE&scm=20140722.H_31848._.OR_help-T_cn~zh-V_1"
author:
published:
created: 2026-07-31
description: "阿里云对象存储OSS（Object Storage Service）是一款海量、安全、低成本、高可靠的云存储服务，可提供99.9999999999%（12个9）的数据持久性，99.995%的数据可用性。多种存储类型供选择，全面优化存储成本。"
tags:
  - "clippings"
---
当需要将不超过5GB的文件上传到OSS，并且对并发上传速度要求不高时，选择简单上传。

**警告**

禁止在开通了 [OSS-HDFS服务](https://help.aliyun.com/zh/oss/user-guide/oss-hdfs/) 的Bucket中，通过非OSS-HDFS服务的方式向数据存储目录`.dlsdata/` 上传Object，以避免影响OSS-HDFS服务的正常使用或引发数据丢失风险。

## 操作方式

使用简单上传前，确保已 [创建存储空间](https://help.aliyun.com/zh/oss/user-guide/create-a-bucket-4) 。

### 使用OSS控制台

**说明**

金融云下的OSS没有公网地域，无法通过控制台上传文件，请通过SDK、ossutil、ossbrowser等方式上传。

1. 登录 [OSS管理控制台](https://oss.console.aliyun.com/) 。
2. 单击 **Bucket 列表** ，然后单击目标Bucket名称。
3. 在左侧导航栏，选择 **文件管理** > **文件列表** 。
4. 在 **文件列表** 页面，单击 **上传文件** 。
5. 在 **上传文件** 面板，选择上传文件或文件夹。
	1. **可选：** 设置基础选项。
		**基础选项**
		<table><tbody><tr><td rowspan="1" colspan="1"><p><b>参数</b></p></td><td rowspan="1" colspan="1"><p><b>说明</b></p></td></tr><tr><td rowspan="1" colspan="1"><p><b>上传到</b></p></td><td rowspan="1" colspan="1"><p>设置文件上传到目标Bucket后的存储路径。</p><ul><li><p><b>当前目录</b> ：将文件上传到当前目录。</p></li><li><p><b>指定目录</b> ：将文件上传到指定目录，您需要输入目录名称。若输入的目录不存在，OSS将自动创建对应的文件目录并将文件上传到该目录中。</p><div><p>目录命名规范如下：</p><ul><li><p>请使用符合要求的UTF-8字符；长度必须在1~254字符之间。</p></li><li><p>不允许以正斜线（/）或反斜线（\）开头。</p></li><li><p>不允许出现连续的正斜线（/）。</p></li><li><p>不允许出现名为 <code> .. </code>的目录。</p></li></ul></div></li></ul></td></tr><tr><td rowspan="1" colspan="1"><p><b>文件 ACL</b></p></td><td rowspan="1" colspan="1"><p>设置文件读写权限ACL。</p><ul><li><p><b>继承 Bucket</b> ：以Bucket读写权限为准。</p></li><li><p><b>私有</b> （推荐）：只有文件Owner拥有该文件的读写权限，其他用户没有权限操作该文件。</p></li><li><p><b>公共读</b> ：文件Owner拥有该文件的读写权限，其他用户（包括匿名访问者）都可以对文件进行访问，这有可能造成您数据的外泄以及费用激增，请谨慎操作。</p></li><li><p><b>公共读写</b> ：任何用户（包括匿名访问者）都可以对文件进行访问，并且向该文件写入数据。这有可能造成您数据的外泄以及费用激增，若被人恶意写入违法信息还可能会侵害您的合法权益。除特殊场景外，不建议您配置公共读写权限。</p></li></ul><p>有关文件ACL的更多信息，请参见 <a href="https://help.aliyun.com/zh/oss/user-guide/object-acl#concept-blw-yqm-2gb">Object ACL</a> 。</p></td></tr><tr><td rowspan="1" colspan="1"><p><b>待上传文件</b></p></td><td rowspan="1" colspan="1"><p>选择您需要上传的文件或文件夹。</p><p>您可以单击 <b>扫描文件</b> 或 <b>扫描文件夹</b> 选择本地文件或文件夹，或者直接拖拽目标文件或文件夹到待上传文件区域。</p><p>如果上传文件夹中包含了无需上传的文件，请单击目标文件右侧的 <b>移除</b> 将其移出文件列表。</p><p><strong>重要</strong></p><div><ul><li><p>在未开启版本控制Bucket中上传文件时，如果上传的文件与已有文件同名，则覆盖已有文件。</p></li><li><p>在已开启版本控制Bucket中上传文件时，如果上传的文件与已有文件同名，则上传文件将成为最新版本，已有文件将成为历史版本。</p></li></ul></div></td></tr></tbody></table>
		2. **可选：** 设置文件存储类型、加密方式等高级选项。
		**高级选项**
		<table><tbody><tr><td rowspan="1" colspan="1"><p><b>参数</b></p></td><td rowspan="1" colspan="1"><p><b>说明</b></p></td></tr><tr><td rowspan="1" colspan="1"><p><b>存储类型</b></p></td><td rowspan="1" colspan="1"><p>设置文件存储类型。</p><ul><li><p><b>继承 Bucket</b> ：以Bucket存储类型为准。</p></li><li><p><b>标准存储</b> ：提供高可靠、高可用、高性能的对象存储服务，能够支持频繁的数据访问。适用于各种社交、分享类的图片、音视频应用、大型网站、大数据分析等业务场景。标准存储类型支持同城冗余ZRS（Zone-redundant storage）和本地冗余LRS（Locally redundant storage）两种数据冗余存储方式。</p></li><li><p><b>低频访问</b> ：提供高持久性、较低存储成本的对象存储服务。有最小计量单位（64 KB）和最低存储时间（30天）的要求。支持数据实时访问，访问数据时会产生数据取回费用，适用于较低访问频率（平均每月访问频率1到2次）的业务场景。低频访问存储支持同城冗余和本地冗余两种数据冗余存储方式。</p></li><li><p><b>归档存储</b> ：提供高持久性、极低存储成本的对象存储服务。有最小计量单位（64 KB）和最低存储时间（60天）要求。归档存储数据支持解冻（约1分钟）后访问或直接访问。解冻后访问会产生归档存储数据取回容量费用，直接访问会产生归档直读数据取回容量费用。归档存储适用于数据长期保存的业务场景，例如档案数据、医疗影像、科学资料、影视素材等。归档存储支持同城冗余和本地冗余两种数据冗余存储方式。</p></li><li><p><b>冷归档存储</b> ：提供高持久性、比归档存储的存储成本更低的对象存储服务。有最小计量单位（64 KB）和最低存储时间（180天）的要求。数据需解冻后访问，解冻时间根据数据大小和选择的解冻模式决定，解冻会产生数据取回费用以及取回请求费用。适用于需要超长时间存放的冷数据，例如因合规要求需要长期留存的数据、大数据及人工智能领域长期积累的原始数据、影视行业长期留存的媒体资源、在线教育行业的归档视频等业务场景。冷归档仅支持本地冗余的数据冗余存储方式。</p></li><li><p><b>深度冷归档存储</b> ：提供高持久性、比冷归档存储成本更低的对象存储服务。有最小计量单位（64 KB）和最低存储时间（180天）的要求。数据需解冻后访问，解冻时间根据数据大小和选择的解冻模式决定，解冻会产生数据取回费用以及取回请求费用。适用于需要超长时间存放的极冷数据，例如大数据及人工智能领域的原始数据的长期积累留存、媒体数据的长期保留、法规和合规性存档、磁带替换等业务场景。深度冷归档仅支持本地冗余的数据冗余存储方式。</p></li></ul><p>更多信息，请参见 <a href="https://help.aliyun.com/zh/oss/user-guide/overview-53/#concept-fcn-3xt-tdb">存储类型介绍</a> 。</p></td></tr><tr><td rowspan="1" colspan="1"><p><b>服务端加密方式</b></p></td><td rowspan="1" colspan="1"><p>设置文件的服务端加密方式。</p><ul><li><p><b>继承 Bucket</b> ：以Bucket的服务端加密方式为准。</p></li><li><p><b>OSS 完全托管</b> ：使用OSS托管的密钥进行加密。OSS会为每个Object使用不同的密钥进行加密，作为额外的保护，OSS会使用主密钥对加密密钥本身进行加密。</p></li><li><p><b>KMS</b> ：使用KMS默认托管的CMK或指定CMK ID进行加解密操作。KMS对应的 <b>加密密钥</b> 说明如下：</p><ul><li><p><b>alias/acs/oss(CMK ID)</b> ：选择该选项后，OSS会使用默认的服务密钥加密Bucket内的数据，并在下载Bucket内的Object时自动进行解密处理。</p></li><li><p><b>alias/<cmkname>(CMK ID</b><b>)</b> ：选择该选项后，OSS会使用指定的服务密钥加密Bucket内的数据，并将加密Object的CMK ID记录到Object的元数据中，具有解密权限的用户下载Object时会自动解密。其中 <code><cmkname></code> 为创建密钥时配置的主密钥可选标识。</p><p>使用指定的CMK ID前，您需要在KMS管理控制台创建一个与Bucket处于相同地域的普通密钥或外部密钥。具体操作，请参见 <a href="https://help.aliyun.com/zh/kms/key-management-service/support/create-a-cmk-1#task-1939967">创建密钥</a> 。</p></li></ul></li><li><p><b>加密算法</b> ：可选择AES256或SM4加密算法。</p></li></ul></td></tr><tr><td rowspan="1" colspan="1"><p><b>用户自定义元数据</b></p></td><td rowspan="1" colspan="1"><p>用于为Object添加描述信息。您可以添加多条自定义元数据（User Meta），但所有的自定义元数据总大小不能超过8 KB。添加自定义元数据时，要求参数以 <code>x-oss-meta-</code> 为前缀，并为参数赋值，例如 <b>x-oss-meta-location:hangzhou</b> 。</p></td></tr></tbody></table>
6. 单击 **上传文件** 。
	此时，您可以在 **上传列表** 页签查看文件的上传进度。

### 使用图形化管理界面ossbrowser

使用ossbrowser简单上传前，确保已 [安装ossbrowser 2.0](https://help.aliyun.com/zh/oss/developer-reference/installing-the-ossbrowser-2-0) 并 [登录ossbrowser 2.0](https://help.aliyun.com/zh/oss/developer-reference/login-to-ossbrowser-2-0) 。

1. 单击目标Bucket名称。
2. 单击 **上传** ，选择上传文件或文件夹。
	此时，您可以在右上角查看文件的上传进度。

### 使用阿里云SDK

上传完整文件

上传字符串

上传Byte数组

上传文件流

上传网络流

上传进度条

上传回调

直接将本地完整文件上传到指定的OSS存储空间（Bucket）中。

Java

Python

Go

Node.js

PHP

Browser.js

.NET

Harmony

Android

iOS

C++

C

Ruby

使用前确保已 [配置访问凭证](https://help.aliyun.com/zh/oss/developer-reference/oss-java-sdk/#1aad0e2f2cft9) 并安装 [OSS Java SDK V1](https://help.aliyun.com/zh/oss/developer-reference/oss-java-sdk/) 。

```java
import com.aliyun.oss.*;
import com.aliyun.oss.common.auth.*;
import com.aliyun.oss.common.comm.SignVersion;
import com.aliyun.oss.model.PutObjectRequest;
import com.aliyun.oss.model.PutObjectResult;
import java.io.File;

public class Demo {

    public static void main(String[] args) throws Exception {
        // Endpoint以华东1（杭州）为例，其它Region请按实际情况填写。
        String endpoint = "https://oss-cn-hangzhou.aliyuncs.com";
        // 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
        EnvironmentVariableCredentialsProvider credentialsProvider = CredentialsProviderFactory.newEnvironmentVariableCredentialsProvider();
        // 填写Bucket名称，例如examplebucket。
        String bucketName = "examplebucket";
        // 填写Object完整路径，完整路径中不能包含Bucket名称，例如exampledir/exampleobject.txt。
        String objectName = "exampledir/exampleobject.txt";
        // 填写本地文件的完整路径，例如D:\\localpath\\examplefile.txt。
        // 如果未指定本地路径，则默认从示例程序所属项目对应本地路径中上传文件。
        String filePath= "D:\\localpath\\examplefile.txt";
        // 填写Bucket所在地域。以华东1（杭州）为例，Region填写为cn-hangzhou。
        String region = "cn-hangzhou";
        
        // 创建OSSClient实例。
        // 当OSSClient实例不再使用时，调用shutdown方法以释放资源。
        ClientBuilderConfiguration clientBuilderConfiguration = new ClientBuilderConfiguration();
        clientBuilderConfiguration.setSignatureVersion(SignVersion.V4);        
        OSS ossClient = OSSClientBuilder.create()
        .endpoint(endpoint)
        .credentialsProvider(credentialsProvider)
        .clientConfiguration(clientBuilderConfiguration)
        .region(region)               
        .build();

        try {
            // 创建PutObjectRequest对象。
            PutObjectRequest putObjectRequest = new PutObjectRequest(bucketName, objectName, new File(filePath));
            // 如果需要上传时设置存储类型和访问权限，请参考以下示例代码。
            // ObjectMetadata metadata = new ObjectMetadata();
            // metadata.setHeader(OSSHeaders.OSS_STORAGE_CLASS, StorageClass.Standard.toString());
            // metadata.setObjectAcl(CannedAccessControlList.Private);
            // putObjectRequest.setMetadata(metadata);
            
            // 上传文件。
            PutObjectResult result = ossClient.putObject(putObjectRequest);           
        } catch (OSSException oe) {
            System.out.println("Caught an OSSException, which means your request made it to OSS, "
                    + "but was rejected with an error response for some reason.");
            System.out.println("Error Message:" + oe.getErrorMessage());
            System.out.println("Error Code:" + oe.getErrorCode());
            System.out.println("Request ID:" + oe.getRequestId());
            System.out.println("Host ID:" + oe.getHostId());
        } catch (ClientException ce) {
            System.out.println("Caught an ClientException, which means the client encountered "
                    + "a serious internal problem while trying to communicate with OSS, "
                    + "such as not being able to access the network.");
            System.out.println("Error Message:" + ce.getMessage());
        } finally {
            if (ossClient != null) {
                ossClient.shutdown();
            }
        }
    }
}
```

使用前确保已 [配置凭证](https://help.aliyun.com/zh/oss/get-started-with-oss-sdk-for-python-v2#745a317b4ci01) 并 [安装OSS Python SDK](https://help.aliyun.com/zh/oss/get-started-with-oss-sdk-for-python-v2#addadb57a9xyy) 。

```python
import argparse
import alibabacloud_oss_v2 as oss

# 创建命令行参数解析器
parser = argparse.ArgumentParser(description="put object from file sample")

# 添加命令行参数 --region，表示存储空间所在的区域，必需参数
parser.add_argument('--region', help='The region in which the bucket is located.', required=True)

# 添加命令行参数 --bucket，表示存储空间的名称，必需参数
parser.add_argument('--bucket', help='The name of the bucket.', required=True)

# 添加命令行参数 --endpoint，表示其他服务可用来访问OSS的域名，非必需参数
parser.add_argument('--endpoint', help='The domain names that other services can use to access OSS')

# 添加命令行参数 --key，表示对象的名称，必需参数
parser.add_argument('--key', help='The name of the object.', required=True)

# 添加命令行参数 --file_path，表示要上传的本地文件路径，必需参数
parser.add_argument('--file_path', help='The path of Upload file.', required=True)

def main():
    # 解析命令行参数
    args = parser.parse_args()

    # 从环境变量中加载凭证信息，用于身份验证
    credentials_provider = oss.credentials.EnvironmentVariableCredentialsProvider()

    # 加载SDK的默认配置，并设置凭证提供者
    cfg = oss.config.load_default()
    cfg.credentials_provider = credentials_provider

    # 设置配置中的区域信息
    cfg.region = args.region

    # 如果提供了endpoint参数，则设置配置中的endpoint
    if args.endpoint is not None:
        cfg.endpoint = args.endpoint

    # 使用配置好的信息创建OSS客户端
    client = oss.Client(cfg)

    # 执行上传对象的请求，直接从文件上传
    # 指定存储空间名称、对象名称和本地文件路径
    result = client.put_object_from_file(
        oss.PutObjectRequest(
            bucket=args.bucket,  # 存储空间名称
            key=args.key         # 对象名称
        ),
        args.file_path          # 本地文件路径
    )

    # 输出请求的结果信息，包括状态码、请求ID、内容MD5、ETag、CRC64校验码、版本ID和服务器响应时间
    print(f'status code: {result.status_code},'
          f' request id: {result.request_id},'
          f' content md5: {result.content_md5},'
          f' etag: {result.etag},'
          f' hash crc64: {result.hash_crc64},'
          f' version id: {result.version_id},'
          f' server time: {result.headers.get("x-oss-server-time")},'
    )

# 脚本入口，当文件被直接运行时调用main函数
if __name__ == "__main__":
    main()
```

使用前确保已 [配置凭证](https://help.aliyun.com/zh/oss/quick-start-for-oss-go-sdk-v2#41f7244e024ul) 并 [安装OSS Go SDK](https://help.aliyun.com/zh/oss/quick-start-for-oss-go-sdk-v2#ff2e78dc863gg) 。

```
package main

import (
    "context"
    "flag"
    "log"

    "github.com/aliyun/alibabacloud-oss-go-sdk-v2/oss"
    "github.com/aliyun/alibabacloud-oss-go-sdk-v2/oss/credentials"
)

// 定义全局变量
var (
    region     string // 存储区域
    bucketName string // 存储空间名称
    objectName string // 对象名称
)

// init函数用于初始化命令行参数
func init() {
    flag.StringVar(&region, "region", "", "The region in which the bucket is located.")
    flag.StringVar(&bucketName, "bucket", "", "The name of the bucket.")
    flag.StringVar(&objectName, "object", "", "The name of the object.")
}

func main() {
    // 解析命令行参数
    flag.Parse()

    // 检查bucket名称是否为空
    if len(bucketName) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, bucket name required")
    }

    // 检查region是否为空
    if len(region) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, region required")
    }

    // 检查object名称是否为空
    if len(objectName) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, object name required")
    }

    // 加载默认配置并设置凭证提供者和区域
    cfg := oss.LoadDefaultConfig().
        WithCredentialsProvider(credentials.NewEnvironmentVariableCredentialsProvider()).
        WithRegion(region)

    // 创建OSS客户端
    client := oss.NewClient(cfg)

    // 填写要上传的本地文件路径和文件名称，例如 /Users/localpath/exampleobject.txt
    localFile := "/Users/localpath/exampleobject.txt"

    // 创建上传对象的请求
    putRequest := &oss.PutObjectRequest{
        Bucket:       oss.Ptr(bucketName),      // 存储空间名称
        Key:          oss.Ptr(objectName),      // 对象名称
        StorageClass: oss.StorageClassStandard, // 指定对象的存储类型为标准存储
        Acl:          oss.ObjectACLPrivate,     // 指定对象的访问权限为私有访问
        Metadata: map[string]string{
            "yourMetadataKey1": "yourMetadataValue1", // 设置对象的元数据
        },
    }

    // 执行上传对象的请求
    result, err := client.PutObjectFromFile(context.TODO(), putRequest, localFile)
    if err != nil {
        log.Fatalf("failed to put object from file %v", err)
    }

    // 打印上传对象的结果
    log.Printf("put object from file result:%#v\n", result)
}
```

```
const OSS = require('ali-oss')
const path=require("path")

const client = new OSS({
  // yourregion填写Bucket所在地域。以华东1（杭州）为例，Region填写为oss-cn-hangzhou。
  region: 'yourregion',
  // 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
  accessKeyId: process.env.OSS_ACCESS_KEY_ID,
  accessKeySecret: process.env.OSS_ACCESS_KEY_SECRET,
  authorizationV4: true,
  // 填写Bucket名称。
  bucket: 'examplebucket',
});

// 自定义请求头
const headers = {
  // 指定Object的存储类型。
  'x-oss-storage-class': 'Standard',
  // 指定Object的访问权限。
  'x-oss-object-acl': 'private',
  // 通过文件URL访问文件时，指定以附件形式下载文件，下载后的文件名称定义为example.txt。
  'Content-Disposition': 'attachment; filename="example.txt"',
  // 设置Object的标签，可同时设置多个标签。
  'x-oss-tagging': 'Tag1=1&Tag2=2',
  // 指定PutObject操作时是否覆盖同名目标Object。此处设置为true，表示禁止覆盖同名Object。
  'x-oss-forbid-overwrite': 'true',
};

async function put () {
  try {
    // 填写OSS文件完整路径和本地文件的完整路径。OSS文件完整路径中不能包含Bucket名称。
    // 如果本地文件的完整路径中未指定本地路径，则默认从示例程序所属项目对应本地路径中上传文件。
    const result = await client.put('exampleobject.txt', path.normalize('D:\\localpath\\examplefile.txt')
    // 自定义headers
    ,{headers}
    );
    console.log(result);
  } catch (e) {
    console.log(e);
  }
}

put();
```

```php
<?php

// 引入自动加载文件，确保依赖库能够正确加载
require_once __DIR__ . '/../vendor/autoload.php';

use AlibabaCloud\Oss\V2 as Oss;

// 定义命令行参数的描述信息
$optsdesc = [
    "region" => ['help' => 'The region in which the bucket is located.', 'required' => True], // Bucket所在的地域（必填）
    "endpoint" => ['help' => 'The domain names that other services can use to access OSS.', 'required' => False], // 访问域名（可选）
    "bucket" => ['help' => 'The name of the bucket', 'required' => True], // Bucket名称（必填）
    "key" => ['help' => 'The name of the object', 'required' => True], // 对象名称（必填）
    "file" => ['help' => 'Local path to the file you want to upload.', 'required' => True], // 本地文件路径（必填）
];

// 将参数描述转换为getopt所需的长选项格式
// 每个参数后面加上":"表示该参数需要值
$longopts = \array_map(function ($key) {
    return "$key:";
}, array_keys($optsdesc));

// 解析命令行参数
$options = getopt("", $longopts);

// 验证必填参数是否存在
foreach ($optsdesc as $key => $value) {
    if ($value['required'] === True && empty($options[$key])) {
        $help = $value['help']; // 获取参数的帮助信息
        echo "Error: the following arguments are required: --$key, $help" . PHP_EOL;
        exit(1); // 如果必填参数缺失，则退出程序
    }
}

// 从解析的参数中提取值
$region = $options["region"]; // Bucket所在的地域
$bucket = $options["bucket"]; // Bucket名称
$key = $options["key"];       // 对象名称
$file = $options["file"];     // 本地文件路径

// 加载环境变量中的凭证信息
// 使用EnvironmentVariableCredentialsProvider从环境变量中读取Access Key ID和Access Key Secret
$credentialsProvider = new Oss\Credentials\EnvironmentVariableCredentialsProvider();

// 使用SDK的默认配置
$cfg = Oss\Config::loadDefault();
$cfg->setCredentialsProvider($credentialsProvider); // 设置凭证提供者
$cfg->setRegion($region); // 设置Bucket所在的地域
if (isset($options["endpoint"])) {
    $cfg->setEndpoint($options["endpoint"]); // 如果提供了访问域名，则设置endpoint
}

// 创建OSS客户端实例
$client = new Oss\Client($cfg);

// 检查文件是否存在
if (!file_exists($file)) {
    echo "Error: The specified file does not exist." . PHP_EOL; // 如果文件不存在，输出错误信息并退出
    exit(1);
}

// 打开文件并准备上传
// 使用fopen以只读模式打开文件，并通过Utils::streamFor将文件内容转换为流
$body = Oss\Utils::streamFor(fopen($file, 'r'));

// 创建PutObjectRequest对象，用于上传文件
$request = new Oss\Models\PutObjectRequest(bucket: $bucket, key: $key);
$request->body = $body; // 设置请求体为文件流

// 执行上传操作
$result = $client->putObject($request);

// 打印上传结果
// 输出HTTP状态码、请求ID和ETag，用于验证上传是否成功
printf(
    'status code:' . $result->statusCode . PHP_EOL . // HTTP状态码，例如200表示成功
    'request id:' . $result->requestId . PHP_EOL .   // 请求ID，用于调试或追踪请求
    'etag:' . $result->etag . PHP_EOL               // 对象的ETag，用于标识对象的唯一性
);
```

```javascript
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Document</title>
  </head>
  <body>
    <input id="file" type="file" />
    <button id="upload">上传</button>
    <script src="https://gosspublic.alicdn.com/aliyun-oss-sdk-6.18.0.min.js"></script>
    <script>
      const client = new OSS({
        // yourRegion填写Bucket所在地域。以华东1（杭州）为例，yourRegion填写为oss-cn-hangzhou。
        region: "yourRegion",
        authorizationV4: true,
        // 从STS服务获取的临时访问密钥（AccessKey ID和AccessKey Secret）。
        accessKeyId: "yourAccessKeyId",
        accessKeySecret: "yourAccessKeySecret",
        // 从STS服务获取的安全令牌（SecurityToken）。
        stsToken: "yourSecurityToken",
        // 填写Bucket名称。
        bucket: "examplebucket",
      });

      // 从输入框获取file对象，例如<input type="file" id="file" />。
      let data;
      // 创建并填写Blob数据。
      //const data = new Blob(['Hello OSS']);
      // 创建并填写OSS Buffer内容。
      //const data = new OSS.Buffer(['Hello OSS']);

      const upload = document.getElementById("upload");

      async function putObject(data) {
        try {
          // 填写Object完整路径。Object完整路径中不能包含Bucket名称。
          // 您可以通过自定义文件名（例如exampleobject.txt）或文件完整路径（例如exampledir/exampleobject.txt）的形式实现将数据上传到当前Bucket或Bucket中的指定目录。
          // data对象可以自定义为file对象、Blob数据或者OSS Buffer。
          const options = {
            meta: { temp: "demo" },
            mime: "json",
            headers: { "Content-Type": "text/plain" },
          };
          const result = await client.put("examplefile.txt", data, options);
          console.log(result);
        } catch (e) {
          console.log(e);
        }
      }

      upload.addEventListener("click", () => {
        const data = file.files[0];
        putObject(data);
      });
    </script>
  </body>
</html>
```

```csharp
using Aliyun.OSS;
using Aliyun.OSS.Common;

// yourEndpoint填写Bucket所在地域对应的Endpoint。以华东1（杭州）为例，Endpoint填写为https://oss-cn-hangzhou.aliyuncs.com。
var endpoint = "yourEndpoint";
// 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
var accessKeyId = Environment.GetEnvironmentVariable("OSS_ACCESS_KEY_ID");
var accessKeySecret = Environment.GetEnvironmentVariable("OSS_ACCESS_KEY_SECRET");
// 填写Bucket名称，例如examplebucket。
var bucketName = "examplebucket";
// 填写Object完整路径，完整路径中不能包含Bucket名称，例如exampledir/exampleobject.txt。
var objectName = "exampledir/exampleobject.txt";
// 填写本地文件的完整路径。如果未指定本地路径，则默认从示例程序所属项目对应本地路径中上传文件。
var localFilename = "D:\\localpath\\examplefile.txt";
// 填写Bucket所在地域对应的Region。以华东1（杭州）为例，Region填写为cn-hangzhou。
const string region = "cn-hangzhou";

// 创建ClientConfiguration实例，按照您的需要修改默认参数。
var conf = new ClientConfiguration();

// 设置v4签名。
conf.SignatureVersion = SignatureVersion.V4;

// 创建OssClient实例。
var client = new OssClient(endpoint, accessKeyId, accessKeySecret, conf);
client.SetRegion(region);
try
{
    // 上传文件。
    client.PutObject(bucketName, objectName, localFilename);
    Console.WriteLine("Put object succeeded");
}
catch (Exception ex)
{
    Console.WriteLine("Put object failed, {0}", ex.Message);
}
```

```
import Client, { RequestError } from '@aliyun/oss';

// 创建OSS客户端实例
const client = new Client({
  // 请替换为STS临时访问凭证的Access Key ID
  accessKeyId: 'yourAccessKeyId',
  // 请替换为STS临时访问凭证的Access Key Secret
  accessKeySecret: 'yourAccessKeySecret',
  // 请替换为STS临时访问凭证的Security Token
  securityToken: 'yourSecurityToken',
  // 填写Bucket所在地域。以华东1（杭州）为例，Region填写为oss-cn-hangzhou
  region: 'oss-cn-hangzhou',
});

const bucket = 'yourBucketName'; // 请替换为您想要使用的Bucket名称

const key = 'yourObjectName'; // 请替换为您想要上传的对象（文件）名称

const putObject = async () => {
  try {
    // 调用putObject方法上传数据到指定的Bucket和Key，并传入数据作为参数
    const res = await client.putObject({
      bucket, // Bucket名称
      key, // 对象（文件）名称
      data: 'hello world' // 要上传的数据，这里是一个简单的字符串
    });

    // 打印上传结果
    console.log(JSON.stringify(res));
  } catch (err) {
    // 捕获请求过程中的异常信息
    if (err instanceof RequestError) {
      // 如果是已知类型的错误，则打印错误代码、错误消息、请求ID、状态码、EC码等信息
      console.log('code: ', err.code);
      console.log('message: ', err.message);
      console.log('requestId: ', err.requestId);
      console.log('status: ', err.status);
      console.log('ec: ', err.ec);
    } else {
      // 打印其他未知类型的错误
      console.log('unknown error: ', err);
    }
  }
}

// 调用putObject函数执行上传操作
putObject();
```

```
// 构造上传请求。
// 依次填写Bucket名称（例如examplebucket）、Object完整路径（例如exampledir/exampleobject.txt）和本地文件完整路径（例如/storage/emulated/0/oss/examplefile.txt）。
// Object完整路径中不能包含Bucket名称。
PutObjectRequest put = new PutObjectRequest("examplebucket", "exampledir/exampleobject.txt", "/storage/emulated/0/oss/examplefile.txt");

// 设置文件元数据为可选操作。
 ObjectMetadata metadata = new ObjectMetadata();
// metadata.setContentType("application/octet-stream"); // 设置content-type。
// metadata.setContentMD5(BinaryUtil.calculateBase64Md5(uploadFilePath)); // 校验MD5。
// 设置Object的访问权限为私有。
metadata.setHeader("x-oss-object-acl", "private");
// 设置Object的存储类型为标准存储。
metadata.setHeader("x-oss-storage-class", "Standard");
// 设置禁止覆盖同名Object。
// metadata.setHeader("x-oss-forbid-overwrite", "true");
// 指定Object的对象标签，可同时设置多个标签。
// metadata.setHeader("x-oss-tagging", "a:1");
// 指定OSS创建目标Object时使用的服务端加密算法 。
// metadata.setHeader("x-oss-server-side-encryption", "AES256");
// 表示KMS托管的用户主密钥，该参数仅在x-oss-server-side-encryption为KMS时有效。
// metadata.setHeader("x-oss-server-side-encryption-key-id", "9468da86-3509-4f8d-a61e-6eab1eac****");

put.setMetadata(metadata);

try {
    PutObjectResult putResult = oss.putObject(put);

    Log.d("PutObject", "UploadSuccess");
    Log.d("ETag", putResult.getETag());
    Log.d("RequestId", putResult.getRequestId());
} catch (ClientException e) {
    // 客户端异常，例如网络异常等。
    e.printStackTrace();
} catch (ServiceException e) {
    // 服务端异常。
    Log.e("RequestId", e.getRequestId());
    Log.e("ErrorCode", e.getErrorCode());
    Log.e("HostId", e.getHostId());
    Log.e("RawMessage", e.getRawMessage());
}
```

```
OSSPutObjectRequest * put = [OSSPutObjectRequest new];

// 填写Bucket名称，例如examplebucket。
put.bucketName = @"examplebucket";
// 填写文件完整路径，例如exampledir/exampleobject.txt。Object完整路径中不能包含Bucket名称。
put.objectKey = @"exampledir/exampleobject.txt";
put.uploadingFileURL = [NSURL fileURLWithPath:@"<filePath>"];
// put.uploadingData = <NSData *>; // 直接上传NSData。

// （可选）设置上传进度。
put.uploadProgress = ^(int64_t bytesSent, int64_t totalByteSent, int64_t totalBytesExpectedToSend) {
    // 指定当前上传长度、当前已经上传总长度、待上传的总长度。
    NSLog(@"%lld, %lld, %lld", bytesSent, totalByteSent, totalBytesExpectedToSend);
};
// 配置可选字段。
// put.contentType = @"application/octet-stream";
// 设置Content-MD5。
// put.contentMd5 = @"eB5eJF1ptWaXm4bijSPyxw==";
// 设置Object的编码方式。
// put.contentEncoding = @"identity";
// 设置Object的展示形式。
// put.contentDisposition = @"attachment";
// 可以在上传文件时设置文件元数据或者HTTP头部。
// NSMutableDictionary *meta = [NSMutableDictionary dictionary];
// 设置文件元数据。
// [meta setObject:@"value" forKey:@"x-oss-meta-name1"];
// 设置Object的访问权限为私有。
// [meta setObject:@"private" forKey:@"x-oss-object-acl"];
// 设置Object的归档类型为标准存储。
// [meta setObject:@"Standard" forKey:@"x-oss-storage-class"];
// 设置覆盖同名目标Object。
// [meta setObject:@"true" forKey:@"x-oss-forbid-overwrite"];
// 指定Object的对象标签，可同时设置多个标签。
// [meta setObject:@"a:1" forKey:@"x-oss-tagging"];
// 指定OSS创建目标Object时使用的服务器端加密算法。
// [meta setObject:@"AES256" forKey:@"x-oss-server-side-encryption"];
// 表示KMS托管的用户主密钥，该参数仅在x-oss-server-side-encryption为KMS时有效。
// [meta setObject:@"9468da86-3509-4f8d-a61e-6eab1eac****" forKey:@"x-oss-server-side-encryption-key-id"];
// put.objectMeta = meta;
OSSTask * putTask = [client putObject:put];

[putTask continueWithBlock:^id(OSSTask *task) {
    if (!task.error) {
        NSLog(@"upload object success!");
    } else {
        NSLog(@"upload object failed, error: %@" , task.error);
    }
    return nil;
}];
// waitUntilFinished会阻塞当前线程，但是不会阻塞上传任务进程。
// [putTask waitUntilFinished];
// [put cancel];
```

```cpp
#include <alibabacloud/oss/OssClient.h>
#include <fstream>
using namespace AlibabaCloud::OSS;

int main(void)
{
    /* 初始化OSS账号信息。*/
            
    /* yourEndpoint填写Bucket所在地域对应的Endpoint。以华东1（杭州）为例，Endpoint填写为https://oss-cn-hangzhou.aliyuncs.com。*/
    std::string Endpoint = "yourEndpoint";
    / *yourRegion填写Bucket所在地域对应的Region。以华东1（杭州）为例，Region填写为cn-hangzhou。 * /
    std::string Region = "yourRegion";
    /* 填写Bucket名称，例如examplebucket。*/
    std::string BucketName = "examplebucket";
    /* 填写Object完整路径，完整路径中不能包含Bucket名称，例如exampledir/exampleobject.txt。*/
    std::string ObjectName = "exampledir/exampleobject.txt";

    /* 初始化网络等资源。*/
    InitializeSdk();

    ClientConfiguration conf;
    conf.signatureVersion = SignatureVersionType::V4;
    /* 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。*/
    auto credentialsProvider = std::make_shared<EnvironmentVariableCredentialsProvider>();
    OssClient client(Endpoint, credentialsProvider, conf);
    client.SetRegion(Region);
    /* 填写本地文件完整路径，例如D:\\localpath\\examplefile.txt，其中localpath为本地文件examplefile.txt所在本地路径。*/
    std::shared_ptr<std::iostream> content = std::make_shared<std::fstream>("D:\\localpath\\examplefile.txt", std::ios::in | std::ios::binary);
    PutObjectRequest request(BucketName, ObjectName, content);

    /*（可选）请参见如下示例设置访问权限ACL为私有（private）以及存储类型为标准存储（Standard）。*/
    //request.MetaData().addHeader("x-oss-object-acl", "private");
    //request.MetaData().addHeader("x-oss-storage-class", "Standard");

    auto outcome = client.PutObject(request);

    if (!outcome.isSuccess()) {
        /* 异常处理。*/
        std::cout << "PutObject fail" <<
        ",code:" << outcome.error().Code() <<
        ",message:" << outcome.error().Message() <<
        ",requestId:" << outcome.error().RequestId() << std::endl;
        return -1;
    }

    /* 释放网络等资源。*/
    ShutdownSdk();
        return 0;
}
```

```c
#include "oss_api.h"
#include "aos_http_io.h"
/* yourEndpoint填写Bucket所在地域对应的Endpoint。以华东1（杭州）为例，Endpoint填写为https://oss-cn-hangzhou.aliyuncs.com。*/
const char *endpoint = "yourEndpoint";
/* 填写Bucket名称，例如examplebucket。*/
const char *bucket_name = "examplebucket";
/* 填写Object完整路径，完整路径中不能包含Bucket名称，例如exampledir/exampleobject.txt。*/
const char *object_name = "exampledir/exampleobject.txt";
const char *object_content = "More than just cloud.";
/* yourRegion填写Bucket所在地域对应的Region。以华东1（杭州）为例，Region填写为cn-hangzhou。*/
const char *region = "yourRegion";
void init_options(oss_request_options_t *options)
{
    options->config = oss_config_create(options->pool);
    /* 用char*类型的字符串初始化aos_string_t类型。*/
    aos_str_set(&options->config->endpoint, endpoint);
    /* 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。*/
    aos_str_set(&options->config->access_key_id, getenv("OSS_ACCESS_KEY_ID"));
    aos_str_set(&options->config->access_key_secret, getenv("OSS_ACCESS_KEY_SECRET"));
    //需要额外配置以下两个参数
    aos_str_set(&options->config->region, region);
    options->config->signature_version = 4;
    /* 是否使用了CNAME。0表示不使用。*/
    options->config->is_cname = 0;
    /* 设置网络相关参数，比如超时时间等。*/
    options->ctl = aos_http_controller_create(options->pool, 0);
}
int main(int argc, char *argv[])
{
    /* 在程序入口调用aos_http_io_initialize方法来初始化网络、内存等全局资源。*/
    if (aos_http_io_initialize(NULL, 0) != AOSE_OK) {
        exit(1);
    }
    /* 用于内存管理的内存池（pool），等价于apr_pool_t。其实现代码在apr库中。*/
    aos_pool_t *pool;
    /* 重新创建一个内存池，第二个参数是NULL，表示没有继承其它内存池。*/
    aos_pool_create(&pool, NULL);
    /* 创建并初始化options，该参数包括endpoint、access_key_id、acces_key_secret、is_cname、curl等全局配置信息。*/
    oss_request_options_t *oss_client_options;
    /* 在内存池中分配内存给options。*/
    oss_client_options = oss_request_options_create(pool);
    /* 初始化Client的选项oss_client_options。*/
    init_options(oss_client_options);
    /* 初始化参数。*/
    aos_string_t bucket;
    aos_string_t object;
    aos_list_t buffer;
    aos_buf_t *content = NULL;
    aos_table_t *headers = NULL;
    aos_table_t *resp_headers = NULL; 
    aos_status_t *resp_status = NULL; 
    aos_str_set(&bucket, bucket_name);
    aos_str_set(&object, object_name);
    aos_list_init(&buffer);
    content = aos_buf_pack(oss_client_options->pool, object_content, strlen(object_content));
    aos_list_add_tail(&content->node, &buffer);
    /* 上传文件。*/
    resp_status = oss_put_object_from_buffer(oss_client_options, &bucket, &object, &buffer, headers, &resp_headers);
    /* 判断上传是否成功。*/
    if (aos_status_is_ok(resp_status)) {
        printf("put object from buffer succeeded\n");
    } else {
        printf("put object from buffer failed\n");      
    }
    /* 释放内存池，相当于释放了请求过程中各资源分配的内存。*/
    aos_pool_destroy(pool);
    /* 释放之前分配的全局资源。*/
    aos_http_io_deinitialize();
    return 0;
}
```

```ruby
require 'aliyun/oss'

client = Aliyun::OSS::Client.new(
  # Endpoint以华东1（杭州）为例，其它Region请按实际情况填写。
  endpoint: 'https://oss-cn-hangzhou.aliyuncs.com',
  # 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
  access_key_id: ENV['OSS_ACCESS_KEY_ID'],
  access_key_secret: ENV['OSS_ACCESS_KEY_SECRET']
)
# 填写Bucket名称，例如examplebucket。
bucket = client.get_bucket('examplebucket')
# 上传文件。
bucket.put_object('exampleobject.txt', :file => 'D:\\localpath\\examplefile.txt')
```

将内存中的字符串内容作为文件直接上传到OSS。

Java

Python

Go

PHP

Node.js

.NET

使用前确保已 [配置访问凭证](https://help.aliyun.com/zh/oss/developer-reference/oss-java-sdk/#1aad0e2f2cft9) 并安装 [OSS Java SDK V1](https://help.aliyun.com/zh/oss/developer-reference/oss-java-sdk/) 。

```java
import com.aliyun.oss.*;
import com.aliyun.oss.common.auth.*;
import com.aliyun.oss.common.comm.SignVersion;
import com.aliyun.oss.model.*;
import java.io.ByteArrayInputStream;

public class Demo {

    public static void main(String[] args) throws Exception {
        // Endpoint以华东1（杭州）为例，其它Region请按实际情况填写。
        String endpoint = "https://oss-cn-hangzhou.aliyuncs.com";
        // 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
        EnvironmentVariableCredentialsProvider credentialsProvider = CredentialsProviderFactory.newEnvironmentVariableCredentialsProvider();
        // 填写Bucket名称，例如examplebucket。
        String bucketName = "examplebucket";
        // 填写Object完整路径，完整路径中不能包含Bucket名称，例如exampledir/exampleobject.txt。
        String objectName = "exampledir/exampleobject.txt";
        // 填写Bucket所在地域。以华东1（杭州）为例，Region填写为cn-hangzhou。
        String region = "cn-hangzhou";
        
        // 创建OSSClient实例。
        // 当OSSClient实例不再使用时，调用shutdown方法以释放资源。
        ClientBuilderConfiguration clientBuilderConfiguration = new ClientBuilderConfiguration();
        clientBuilderConfiguration.setSignatureVersion(SignVersion.V4);        
        OSS ossClient = OSSClientBuilder.create()
        .endpoint(endpoint)
        .credentialsProvider(credentialsProvider)
        .clientConfiguration(clientBuilderConfiguration)
        .region(region)               
        .build();

        try {
            // 填写字符串。
            String content = "Hello OSS，你好世界";

            // 创建PutObjectRequest对象。
            PutObjectRequest putObjectRequest = new PutObjectRequest(bucketName, objectName, new ByteArrayInputStream(content.getBytes()));

            // 如果需要上传时设置存储类型和访问权限，请参考以下示例代码。
            // ObjectMetadata metadata = new ObjectMetadata();
            // metadata.setHeader(OSSHeaders.OSS_STORAGE_CLASS, StorageClass.Standard.toString());
            // metadata.setObjectAcl(CannedAccessControlList.Private);
            // putObjectRequest.setMetadata(metadata);
           
            // 上传字符串。
            PutObjectResult result = ossClient.putObject(putObjectRequest);            
        } catch (OSSException oe) {
            System.out.println("Caught an OSSException, which means your request made it to OSS, "
                    + "but was rejected with an error response for some reason.");
            System.out.println("Error Message:" + oe.getErrorMessage());
            System.out.println("Error Code:" + oe.getErrorCode());
            System.out.println("Request ID:" + oe.getRequestId());
            System.out.println("Host ID:" + oe.getHostId());
        } catch (ClientException ce) {
            System.out.println("Caught an ClientException, which means the client encountered "
                    + "a serious internal problem while trying to communicate with OSS, "
                    + "such as not being able to access the network.");
            System.out.println("Error Message:" + ce.getMessage());
        } finally {
            if (ossClient != null) {
                ossClient.shutdown();
            }
        }
    }
}
```

使用前确保已 [配置凭证](https://help.aliyun.com/zh/oss/get-started-with-oss-sdk-for-python-v2#745a317b4ci01) 并 [安装OSS Python SDK](https://help.aliyun.com/zh/oss/get-started-with-oss-sdk-for-python-v2#addadb57a9xyy) 。

```python
import argparse
import alibabacloud_oss_v2 as oss

# 创建命令行参数解析器
parser = argparse.ArgumentParser(description="put object sample")
# 添加命令行参数 --region，表示存储空间所在的区域，必需参数
parser.add_argument('--region', help='The region in which the bucket is located.', required=True)
# 添加命令行参数 --bucket，表示存储空间的名称，必需参数
parser.add_argument('--bucket', help='The name of the bucket.', required=True)
# 添加命令行参数 --endpoint，表示其他服务可用来访问OSS的域名，非必需参数
parser.add_argument('--endpoint', help='The domain names that other services can use to access OSS')
# 添加命令行参数 --key，表示对象的名称，必需参数
parser.add_argument('--key', help='The name of the object.', required=True)

def main():
    args = parser.parse_args()  # 解析命令行参数

    # 从环境变量中加载凭证信息，用于身份验证
    credentials_provider = oss.credentials.EnvironmentVariableCredentialsProvider()

    # 加载SDK的默认配置，并设置凭证提供者
    cfg = oss.config.load_default()
    cfg.credentials_provider = credentials_provider
    # 设置配置中的区域信息
    cfg.region = args.region
    # 如果提供了endpoint参数，则设置配置中的endpoint
    if args.endpoint is not None:
        cfg.endpoint = args.endpoint

    # 使用配置好的信息创建OSS客户端
    client = oss.Client(cfg)

    # 定义要上传的字符串内容
    text_string = "Hello, OSS!"
    data = text_string.encode('utf-8')  # 将字符串编码为UTF-8字节串

    # 执行上传对象的请求，指定存储空间名称、对象名称和数据内容
    result = client.put_object(oss.PutObjectRequest(
        bucket=args.bucket,
        key=args.key,
        body=data,
    ))

    # 输出请求的结果状态码、请求ID、内容MD5、ETag、CRC64校验码和版本ID，用于检查请求是否成功
    print(f'status code: {result.status_code},'
          f' request id: {result.request_id},'
          f' content md5: {result.content_md5},'
          f' etag: {result.etag},'
          f' hash crc64: {result.hash_crc64},'
          f' version id: {result.version_id},'
    )

if __name__ == "__main__":
    main()  # 脚本入口，当文件被直接运行时调用main函数
```

使用前确保已 [配置凭证](https://help.aliyun.com/zh/oss/quick-start-for-oss-go-sdk-v2#41f7244e024ul) 并 [安装OSS Go SDK](https://help.aliyun.com/zh/oss/quick-start-for-oss-go-sdk-v2#ff2e78dc863gg) 。

```
package main

import (
    "context"
    "flag"
    "log"
    "strings"

    "github.com/aliyun/alibabacloud-oss-go-sdk-v2/oss"
    "github.com/aliyun/alibabacloud-oss-go-sdk-v2/oss/credentials"
)

// 定义全局变量
var (
    region     string // 存储区域
    bucketName string // 存储空间名称
    objectName string // 对象名称
)

// init函数用于初始化命令行参数
func init() {
    flag.StringVar(&region, "region", "", "The region in which the bucket is located.")
    flag.StringVar(&bucketName, "bucket", "", "The name of the bucket.")
    flag.StringVar(&objectName, "object", "", "The name of the object.")
}

func main() {
    // 解析命令行参数
    flag.Parse()

    // 检查bucket名称是否为空
    if len(bucketName) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, bucket name required")
    }

    // 检查region是否为空
    if len(region) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, region required")
    }

    // 检查object名称是否为空
    if len(objectName) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, object name required")
    }

    // 定义要上传的字符串内容
    body := strings.NewReader("hi oss")

    // 加载默认配置并设置凭证提供者和区域
    cfg := oss.LoadDefaultConfig().
        WithCredentialsProvider(credentials.NewEnvironmentVariableCredentialsProvider()).
        WithRegion(region)

    // 创建OSS客户端
    client := oss.NewClient(cfg)

    // 创建上传对象的请求
    request := &oss.PutObjectRequest{
        Bucket: oss.Ptr(bucketName), // 存储空间名称
        Key:    oss.Ptr(objectName), // 对象名称
        Body:   body,                // 要上传的字符串内容
    }

    // 发送上传对象的请求
    result, err := client.PutObject(context.TODO(), request)
    if err != nil {
        log.Fatalf("failed to put object %v", err)
    }

    // 打印上传对象的结果
    log.Printf("put object result:%#v\n", result)
}
```

```php
<?php

// 引入自动加载文件，确保依赖库能够正确加载
require_once __DIR__ . '/../vendor/autoload.php';

use AlibabaCloud\Oss\V2 as Oss;

// 定义命令行参数的描述信息
$optsdesc = [
    "region" => ['help' => 'The region in which the bucket is located.', 'required' => True], // Bucket所在的地域（必填）
    "endpoint" => ['help' => 'The domain names that other services can use to access OSS.', 'required' => False], // 访问域名（可选）
    "bucket" => ['help' => 'The name of the bucket', 'required' => True], // Bucket名称（必填）
    "key" => ['help' => 'The name of the object', 'required' => True], // 对象名称（必填）
];

// 将参数描述转换为getopt所需的长选项格式
$longopts = \array_map(function ($key) {
    return "$key:"; // 每个参数后面加上":"表示需要值
}, array_keys($optsdesc));

// 解析命令行参数
$options = getopt("", $longopts);

// 验证必填参数是否存在
foreach ($optsdesc as $key => $value) {
    if ($value['required'] === True && empty($options[$key])) {
        $help = $value['help']; // 获取参数的帮助信息
        echo "Error: the following arguments are required: --$key, $help" . PHP_EOL;
        exit(1); // 如果必填参数缺失，则退出程序
    }
}

// 从解析的参数中提取值
$region = $options["region"]; // Bucket所在的地域
$bucket = $options["bucket"]; // Bucket名称
$key = $options["key"];       // 对象名称

// 加载环境变量中的凭证信息
// 使用EnvironmentVariableCredentialsProvider从环境变量中读取Access Key ID和Access Key Secret
$credentialsProvider = new Oss\Credentials\EnvironmentVariableCredentialsProvider();

// 使用SDK的默认配置
$cfg = Oss\Config::loadDefault();
$cfg->setCredentialsProvider($credentialsProvider); // 设置凭证提供者
$cfg->setRegion($region); // 设置Bucket所在的地域
if (isset($options["endpoint"])) {
    $cfg->setEndpoint($options["endpoint"]); // 如果提供了访问域名，则设置endpoint
}

// 创建OSS客户端实例
$client = new Oss\Client($cfg);

// 要上传的数据内容
$data = 'Hello OSS';

// 创建PutObjectRequest对象，用于上传对象
$request = new Oss\Models\PutObjectRequest(bucket: $bucket, key: $key);
$request->body = Oss\Utils::streamFor($data); // 设置请求体为数据流

// 执行上传操作
$result = $client->putObject($request);

// 打印上传结果
printf(
    'status code: %s' . PHP_EOL . // HTTP状态码
    'request id: %s' . PHP_EOL .  // 请求ID
    'etag: %s' . PHP_EOL,         // 对象的ETag
    $result->statusCode,
    $result->requestId,
    $result->etag
);
```

```
const OSS = require('ali-oss');

const client = new OSS({
  // yourregion填写Bucket所在地域。以华东1（杭州）为例，Region填写为oss-cn-hangzhou。
  region: 'yourregion',
  // 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
  accessKeyId: process.env.OSS_ACCESS_KEY_ID,
  accessKeySecret: process.env.OSS_ACCESS_KEY_SECRET,
  authorizationV4: true,
  // yourbucketname填写存储空间名称。
  bucket: 'yourbucketname',
});

async function putBuffer () {
  try {
    const result = await client.put('object-name', new Buffer.from('hello world'));
    console.log(result);
  } catch (e) {
    console.log(e);
  }
}

putBuffer();
```

```csharp
using System.Text;
using Aliyun.OSS;
using Aliyun.OSS.Common;

// yourEndpoint填写Bucket所在地域对应的Endpoint。以华东1（杭州）为例，Endpoint填写为https://oss-cn-hangzhou.aliyuncs.com。
var endpoint = "yourEndpoint";
// 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
var accessKeyId = Environment.GetEnvironmentVariable("OSS_ACCESS_KEY_ID");
var accessKeySecret = Environment.GetEnvironmentVariable("OSS_ACCESS_KEY_SECRET");
// 填写Bucket名称，例如examplebucket。
var bucketName = "examplebucket";
// 填写Object完整路径，完整路径中不能包含Bucket名称，例如exampledir/exampleobject.txt。
var objectName = "exampledir/exampleobject.txt";
// 填写字符串。
var objectContent = "More than just cloud.";
// 填写Bucket所在地域对应的Region。以华东1（杭州）为例，Region填写为cn-hangzhou。
const string region = "cn-hangzhou";

// 创建ClientConfiguration实例，按照您的需要修改默认参数。
var conf = new ClientConfiguration();

// 设置v4签名。
conf.SignatureVersion = SignatureVersion.V4;

// 创建OssClient实例。
var client = new OssClient(endpoint, accessKeyId, accessKeySecret, conf);
client.SetRegion(region);
try
{
    byte[] binaryData = Encoding.ASCII.GetBytes(objectContent);
    MemoryStream requestContent = new MemoryStream(binaryData);
    // 上传文件。
    client.PutObject(bucketName, objectName, requestContent);
    Console.WriteLine("Put object succeeded");
}
catch (Exception ex)
{
    Console.WriteLine("Put object failed, {0}", ex.Message);
}
```

将内存中的字节数组作为文件内容上传，适用于对二进制数据进行灵活处理后再上传的需求。

使用前确保已 [配置凭证](https://help.aliyun.com/zh/oss/get-started-with-oss-sdk-for-python-v2#745a317b4ci01) 并 [安装OSS Python SDK](https://help.aliyun.com/zh/oss/get-started-with-oss-sdk-for-python-v2#addadb57a9xyy) 。

```python
import argparse
import alibabacloud_oss_v2 as oss

# 创建命令行参数解析器
parser = argparse.ArgumentParser(description="put object sample")
# 添加命令行参数 --region，表示存储空间所在的区域，必需参数
parser.add_argument('--region', help='The region in which the bucket is located.', required=True)
# 添加命令行参数 --bucket，表示存储空间的名称，必需参数
parser.add_argument('--bucket', help='The name of the bucket.', required=True)
# 添加命令行参数 --endpoint，表示其他服务可用来访问OSS的域名，非必需参数
parser.add_argument('--endpoint', help='The domain names that other services can use to access OSS')
# 添加命令行参数 --key，表示对象的名称，必需参数
parser.add_argument('--key', help='The name of the object.', required=True)

def main():
    args = parser.parse_args()  # 解析命令行参数

    # 从环境变量中加载凭证信息，用于身份验证
    credentials_provider = oss.credentials.EnvironmentVariableCredentialsProvider()

    # 加载SDK的默认配置，并设置凭证提供者
    cfg = oss.config.load_default()
    cfg.credentials_provider = credentials_provider
    # 设置配置中的区域信息
    cfg.region = args.region
    # 如果提供了endpoint参数，则设置配置中的endpoint
    if args.endpoint is not None:
        cfg.endpoint = args.endpoint

    # 使用配置好的信息创建OSS客户端
    client = oss.Client(cfg)

    # 定义要上传的数据内容
    data = b'hello world'

    # 执行上传对象的请求，指定存储空间名称、对象名称和数据内容
    result = client.put_object(oss.PutObjectRequest(
        bucket=args.bucket,
        key=args.key,
        body=data,
    ))

    # 输出请求的结果状态码、请求ID、内容MD5、ETag、CRC64校验码和版本ID，用于检查请求是否成功
    print(f'status code: {result.status_code},'
          f' request id: {result.request_id},'
          f' content md5: {result.content_md5},'
          f' etag: {result.etag},'
          f' hash crc64: {result.hash_crc64},'
          f' version id: {result.version_id},'
    )

if __name__ == "__main__":
    main()  # 脚本入口，当文件被直接运行时调用main函数
```

使用前确保已 [配置凭证](https://help.aliyun.com/zh/oss/quick-start-for-oss-go-sdk-v2#41f7244e024ul) 并 [安装OSS Go SDK](https://help.aliyun.com/zh/oss/quick-start-for-oss-go-sdk-v2#ff2e78dc863gg) 。

```
package main

import (
    "bytes"
    "context"
    "flag"
    "log"

    "github.com/aliyun/alibabacloud-oss-go-sdk-v2/oss"
    "github.com/aliyun/alibabacloud-oss-go-sdk-v2/oss/credentials"
)

// 定义全局变量
var (
    region     string // 存储区域
    bucketName string // 存储空间名称
    objectName string // 对象名称
)

// init函数用于初始化命令行参数
func init() {
    flag.StringVar(&region, "region", "", "The region in which the bucket is located.")
    flag.StringVar(&bucketName, "bucket", "", "The name of the bucket.")
    flag.StringVar(&objectName, "object", "", "The name of the object.")
}

func main() {
    // 解析命令行参数
    flag.Parse()

    // 检查bucket名称是否为空
    if len(bucketName) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, bucket name required")
    }

    // 检查region是否为空
    if len(region) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, region required")
    }

    // 检查object名称是否为空
    if len(objectName) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, object name required")
    }

    // 定义要上传的byte数组内容
    body := bytes.NewReader([]byte("yourObjectValueByteArray"))

    // 加载默认配置并设置凭证提供者和区域
    cfg := oss.LoadDefaultConfig().
        WithCredentialsProvider(credentials.NewEnvironmentVariableCredentialsProvider()).
        WithRegion(region)

    // 创建OSS客户端
    client := oss.NewClient(cfg)

    // 创建上传对象的请求
    request := &oss.PutObjectRequest{
        Bucket: oss.Ptr(bucketName), // 存储空间名称
        Key:    oss.Ptr(objectName), // 对象名称
        Body:   body,                // 要上传的字符串内容
    }

    // 发送上传对象的请求
    result, err := client.PutObject(context.TODO(), request)
    if err != nil {
        log.Fatalf("failed to put object %v", err)
    }

    // 打印上传对象的结果
    log.Printf("put object result:%#v\n", result)
}
```

```
byte[] uploadData = new byte[100 * 1024];
new Random().nextBytes(uploadData);

// 构造上传请求。
// 依次填写Bucket名称（例如examplebucket）和Object完整路径（例如exampledir/exampleobject.txt）。
// Object完整路径中不能包含Bucket名称。
PutObjectRequest put = new PutObjectRequest("examplebucket", "exampledir/exampleobject.txt", uploadData);

try {
    PutObjectResult putResult = oss.putObject(put);

    Log.d("PutObject", "UploadSuccess");
    Log.d("ETag", putResult.getETag());
    Log.d("RequestId", putResult.getRequestId());
} catch (ClientException e) {
    // 客户端异常，例如网络异常等。
    e.printStackTrace();
} catch (ServiceException e) {
    // 服务端异常。
    Log.e("RequestId", e.getRequestId());
    Log.e("ErrorCode", e.getErrorCode());
    Log.e("HostId", e.getHostId());
    Log.e("RawMessage", e.getRawMessage());
}
```

通过文件输入流读取本地或内存中的数据并上传。

使用前确保已 [配置访问凭证](https://help.aliyun.com/zh/oss/developer-reference/oss-java-sdk/#1aad0e2f2cft9) 并安装 [OSS Java SDK V1](https://help.aliyun.com/zh/oss/developer-reference/oss-java-sdk/) 。

```java
import com.aliyun.oss.*;
import com.aliyun.oss.common.auth.*;
import com.aliyun.oss.common.comm.SignVersion;
import com.aliyun.oss.model.PutObjectRequest;
import com.aliyun.oss.model.PutObjectResult;
import java.io.FileInputStream;
import java.io.InputStream;

public class Demo {

    public static void main(String[] args) throws Exception {
        // Endpoint以华东1（杭州）为例，其它Region请按实际情况填写。
        String endpoint = "https://oss-cn-hangzhou.aliyuncs.com";
        // 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
        EnvironmentVariableCredentialsProvider credentialsProvider = CredentialsProviderFactory.newEnvironmentVariableCredentialsProvider();
        // 填写Bucket名称，例如examplebucket。
        String bucketName = "examplebucket";
        // 填写Object完整路径，完整路径中不能包含Bucket名称，例如exampledir/exampleobject.txt。
        String objectName = "exampledir/exampleobject.txt";
        // 填写本地文件的完整路径，例如D:\\localpath\\examplefile.txt。
        // 如果未指定本地路径，则默认从示例程序所属项目对应本地路径中上传文件流。
        String filePath= "D:\\localpath\\examplefile.txt";
        // 填写Bucket所在地域。以华东1（杭州）为例，Region填写为cn-hangzhou。
        String region = "cn-hangzhou";
        
        // 创建OSSClient实例。
        // 当OSSClient实例不再使用时，调用shutdown方法以释放资源。
        ClientBuilderConfiguration clientBuilderConfiguration = new ClientBuilderConfiguration();
        clientBuilderConfiguration.setSignatureVersion(SignVersion.V4);        
        OSS ossClient = OSSClientBuilder.create()
        .endpoint(endpoint)
        .credentialsProvider(credentialsProvider)
        .clientConfiguration(clientBuilderConfiguration)
        .region(region)               
        .build();

        try {
            InputStream inputStream = new FileInputStream(filePath);
            // 创建PutObjectRequest对象。
            PutObjectRequest putObjectRequest = new PutObjectRequest(bucketName, objectName, inputStream);
            // 创建PutObject请求。
            PutObjectResult result = ossClient.putObject(putObjectRequest);
        } catch (OSSException oe) {
            System.out.println("Caught an OSSException, which means your request made it to OSS, "
                    + "but was rejected with an error response for some reason.");
            System.out.println("Error Message:" + oe.getErrorMessage());
            System.out.println("Error Code:" + oe.getErrorCode());
            System.out.println("Request ID:" + oe.getRequestId());
            System.out.println("Host ID:" + oe.getHostId());
        } catch (ClientException ce) {
            System.out.println("Caught an ClientException, which means the client encountered "
                    + "a serious internal problem while trying to communicate with OSS, "
                    + "such as not being able to access the network.");
            System.out.println("Error Message:" + ce.getMessage());
        } finally {
            if (ossClient != null) {
                ossClient.shutdown();
            }
        }
    }
}
```

```js
const OSS = require('ali-oss');
const fs = require('fs');
const client = new OSS({
  // yourRegion填写Bucket所在地域。以华东1（杭州）为例，Region填写为oss-cn-hangzhou。
  region: 'yourRegion',
  // 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
  accessKeyId: process.env.OSS_ACCESS_KEY_ID,
  accessKeySecret: process.env.OSS_ACCESS_KEY_SECRET,
  authorizationV4: true,
  // 填写Bucket名称，例如examplebucket。
  bucket: 'examplebucket',
});

async function putStream () {
  try {
    // 使用chunked encoding。使用putStream接口时，SDK默认会发起一个chunked encoding的HTTP PUT请求。
    // 填写本地文件的完整路径，从本地文件中读取数据流。
    // 如果本地文件的完整路径中未指定本地路径，则默认从示例程序所属项目对应本地路径中上传文件。
    let stream = fs.createReadStream('D:\\localpath\\examplefile.txt');
    // 填写Object完整路径，例如exampledir/exampleobject.txt。Object完整路径中不能包含Bucket名称。
    let result = await client.putStream('exampledir/exampleobject.txt', stream);    

    // 不使用chunked encoding。如果在options指定了contentLength参数，则不会使用chunked encoding。
    // let stream = fs.createReadStream('D:\\localpath\\examplefile.txt');
    // let size = fs.statSync('D:\\localpath\\examplefile.txt').size;
    // let result = await client.putStream(
    // stream参数可以是任何实现了Readable Stream的对象，包含文件流，网络流等。
    // 'exampledir/exampleobject.txt', stream, {contentLength: size}); 
    console.log(result); 
  } catch (e) {
    console.log(e)
  }
}

putStream();
```

```ruby
require 'aliyun/oss'

client = Aliyun::OSS::Client.new(
  # Endpoint以华东1（杭州）为例，其它Region请按实际情况填写。  
  endpoint: 'https://oss-cn-hangzhou.aliyuncs.com',
  # 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
  access_key_id: ENV['OSS_ACCESS_KEY_ID'],
  access_key_secret: ENV['OSS_ACCESS_KEY_SECRET']
)

# 填写Bucket名称，例如examplebucket。
bucket = client.get_bucket('examplebucket')
# 填写Object完整路径，完整路径中不能包含Bucket名称，例如exampleobject.txt。
bucket.put_object('exampleobject.txt') do |stream|
  100.times { |i| stream << i.to_s }
end
```

直接读取网络上的数据流并上传到OSS，适用于无需本地落盘的流式数据转存需求。

Java

Python

Go

Node.js

PHP

使用前确保已 [配置访问凭证](https://help.aliyun.com/zh/oss/developer-reference/oss-java-sdk/#1aad0e2f2cft9) 并安装 [OSS Java SDK V1](https://help.aliyun.com/zh/oss/developer-reference/oss-java-sdk/) 。

```java
import com.aliyun.oss.*;
import com.aliyun.oss.common.auth.*;
import com.aliyun.oss.common.comm.SignVersion;
import com.aliyun.oss.model.PutObjectRequest;
import com.aliyun.oss.model.PutObjectResult;
import java.io.InputStream;
import java.net.URL;

public class Demo {

    public static void main(String[] args) throws Exception {
        // Endpoint以华东1（杭州）为例，其它Region请按实际情况填写。
        String endpoint = "https://oss-cn-hangzhou.aliyuncs.com";
        // 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
        EnvironmentVariableCredentialsProvider credentialsProvider = CredentialsProviderFactory.newEnvironmentVariableCredentialsProvider();
        // 填写Bucket名称，例如examplebucket。
        String bucketName = "examplebucket";
        // 填写Object完整路径，完整路径中不能包含Bucket名称，例如exampledir/exampleobject.txt。
        String objectName = "exampledir/exampleobject.txt";
        // 填写网络流地址。
        String url = "https://www.aliyun.com/";
        // 填写Bucket所在地域。以华东1（杭州）为例，Region填写为cn-hangzhou。
        String region = "cn-hangzhou";
        
        // 创建OSSClient实例。
        // 当OSSClient实例不再使用时，调用shutdown方法以释放资源。
        ClientBuilderConfiguration clientBuilderConfiguration = new ClientBuilderConfiguration();
        clientBuilderConfiguration.setSignatureVersion(SignVersion.V4);        
        OSS ossClient = OSSClientBuilder.create()
        .endpoint(endpoint)
        .credentialsProvider(credentialsProvider)
        .clientConfiguration(clientBuilderConfiguration)
        .region(region)               
        .build();

        try {
            InputStream inputStream = new URL(url).openStream();
            // 创建PutObjectRequest对象。
            PutObjectRequest putObjectRequest = new PutObjectRequest(bucketName, objectName, inputStream);
            // 创建PutObject请求。
            PutObjectResult result = ossClient.putObject(putObjectRequest);            
        } catch (OSSException oe) {
            System.out.println("Caught an OSSException, which means your request made it to OSS, "
                    + "but was rejected with an error response for some reason.");
            System.out.println("Error Message:" + oe.getErrorMessage());
            System.out.println("Error Code:" + oe.getErrorCode());
            System.out.println("Request ID:" + oe.getRequestId());
            System.out.println("Host ID:" + oe.getHostId());
        } catch (ClientException ce) {
            System.out.println("Caught an ClientException, which means the client encountered "
                    + "a serious internal problem while trying to communicate with OSS, "
                    + "such as not being able to access the network.");
            System.out.println("Error Message:" + ce.getMessage());
        } finally {
            if (ossClient != null) {
                ossClient.shutdown();
            }
        }
    }
}
```

使用前确保已 [配置凭证](https://help.aliyun.com/zh/oss/get-started-with-oss-sdk-for-python-v2#745a317b4ci01) 并 [安装OSS Python SDK](https://help.aliyun.com/zh/oss/get-started-with-oss-sdk-for-python-v2#addadb57a9xyy) 。

```python
import argparse
import requests
import alibabacloud_oss_v2 as oss

# 创建命令行参数解析器
parser = argparse.ArgumentParser(description="put object sample")
# 添加命令行参数 --region，表示存储空间所在的区域，必需参数
parser.add_argument('--region', help='The region in which the bucket is located.', required=True)
# 添加命令行参数 --bucket，表示存储空间的名称，必需参数
parser.add_argument('--bucket', help='The name of the bucket.', required=True)
# 添加命令行参数 --endpoint，表示其他服务可用来访问OSS的域名，非必需参数
parser.add_argument('--endpoint', help='The domain names that other services can use to access OSS')
# 添加命令行参数 --key，表示对象的名称，必需参数
parser.add_argument('--key', help='The name of the object.', required=True)

def main():
    args = parser.parse_args()  # 解析命令行参数

    # 从环境变量中加载凭证信息，用于身份验证
    credentials_provider = oss.credentials.EnvironmentVariableCredentialsProvider()

    # 加载SDK的默认配置，并设置凭证提供者
    cfg = oss.config.load_default()
    cfg.credentials_provider = credentials_provider
    # 设置配置中的区域信息
    cfg.region = args.region
    # 如果提供了endpoint参数，则设置配置中的endpoint
    if args.endpoint is not None:
        cfg.endpoint = args.endpoint

    # 使用配置好的信息创建OSS客户端
    client = oss.Client(cfg)

    # 发送HTTP GET请求，获取响应内容
    response = requests.get('http://www.aliyun.com')

    # 执行上传对象的请求，指定存储空间名称、对象名称和数据内容
    result = client.put_object(oss.PutObjectRequest(
        bucket=args.bucket,
        key=args.key,
        body=response.content,
    ))

    # 输出请求的结果状态码、请求ID、内容MD5、ETag、CRC64校验码和版本ID，用于检查请求是否成功
    print(f'status code: {result.status_code},'
          f' request id: {result.request_id},'
          f' content md5: {result.content_md5},'
          f' etag: {result.etag},'
          f' hash crc64: {result.hash_crc64},'
          f' version id: {result.version_id},'
    )

if __name__ == "__main__":
    main()  # 脚本入口，当文件被直接运行时调用main函数
```

使用前确保已 [配置凭证](https://help.aliyun.com/zh/oss/quick-start-for-oss-go-sdk-v2#41f7244e024ul) 并 [安装OSS Go SDK](https://help.aliyun.com/zh/oss/quick-start-for-oss-go-sdk-v2#ff2e78dc863gg) 。

```
package main

import (
    "context"
    "flag"
    "io"
    "log"
    "net/http"

    "github.com/aliyun/alibabacloud-oss-go-sdk-v2/oss"
    "github.com/aliyun/alibabacloud-oss-go-sdk-v2/oss/credentials"
)

// 定义全局变量
var (
    region     string // 存储区域
    bucketName string // 存储空间名称
    objectName string // 对象名称
)

// init函数用于初始化命令行参数
func init() {
    flag.StringVar(&region, "region", "", "The region in which the bucket is located.")
    flag.StringVar(&bucketName, "bucket", "", "The name of the bucket.")
    flag.StringVar(&objectName, "object", "", "The name of the object.")
}

func main() {
    // 解析命令行参数
    flag.Parse()

    // 检查bucket名称是否为空
    if len(bucketName) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, bucket name required")
    }

    // 检查region是否为空
    if len(region) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, region required")
    }

    // 检查object名称是否为空
    if len(objectName) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, object name required")
    }

    // 加载默认配置并设置凭证提供者和区域
    cfg := oss.LoadDefaultConfig().
        WithCredentialsProvider(credentials.NewEnvironmentVariableCredentialsProvider()).
        WithRegion(region)

    // 创建OSS客户端
    client := oss.NewClient(cfg)

    // 指定待上传的网络流
    resp, err := http.Get("https://www.aliyun.com/")
    if err != nil {
        log.Fatalf("Failed to fetch URL: %v", err)
    }
    defer resp.Body.Close()

    // 创建上传对象的请求
    request := &oss.PutObjectRequest{
        Bucket: oss.Ptr(bucketName),  // 存储空间名称
        Key:    oss.Ptr(objectName),  // 对象名称
        Body:   io.Reader(resp.Body), // 要上传的网络流内容
    }

    // 发送上传对象的请求
    result, err := client.PutObject(context.TODO(), request)
    if err != nil {
        log.Fatalf("failed to put object %v", err)
    }

    // 打印上传对象的结果
    log.Printf("put object result:%#v\n", result)
}
```

```
const OSS = require("ali-oss");
const fs = require("fs");
const urllib = require("urllib"); 

const client = new OSS({  
  // yourRegion填写Bucket所在地域。以华东1（杭州）为例，Region填写为oss-cn-hangzhou。
  region: 'yourRegion',
  // 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
  accessKeyId: process.env.OSS_ACCESS_KEY_ID,
  accessKeySecret: process.env.OSS_ACCESS_KEY_SECRET,
  authorizationV4: true,
  // 填写Bucket名称，例如examplebucket。
  bucket: 'examplebucket',
});

// 指定网络流URL。
const url = "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20220908/cbgh/图片处理_example.jpg";
// 导入双工流。
// stream参数可以是任何实现了Readable Stream的对象，包含文件流，网络流等。
const Duplex = require("stream").Duplex;
// 实例化双工流。
let stream = new Duplex();

urllib.request(url, (err, data, res) => {
  if (!err) {
    // 通过双工流接收数据。
    stream.push(data);
    stream.push(null);

    client
      // 填写Object完整路径，例如example.png。Object完整路径中不能包含Bucket名称。
      .putStream("example.png", stream)
      .then((r) => console.log(r))
      .catch((e) => console.log(e));
  }
});
```

```php
<?php

// 引入自动加载文件，确保依赖库能够正确加载
require_once __DIR__ . '/../vendor/autoload.php';

use AlibabaCloud\Oss\V2 as Oss;

// 定义命令行参数的描述信息
$optsdesc = [
    "region" => ['help' => 'The region in which the bucket is located.', 'required' => True], // Bucket所在的地域（必填）
    "endpoint" => ['help' => 'The domain names that other services can use to access OSS.', 'required' => False], // 访问域名（可选）
    "bucket" => ['help' => 'The name of the bucket', 'required' => True], // Bucket名称（必填）
    "key" => ['help' => 'The name of the object', 'required' => True], // 对象名称（必填）
];

// 将参数描述转换为getopt所需的长选项格式
$longopts = \array_map(function ($key) {
    return "$key:"; // 每个参数后面加上":"表示需要值
}, array_keys($optsdesc));

// 解析命令行参数
$options = getopt("", $longopts);

// 验证必填参数是否存在
foreach ($optsdesc as $key => $value) {
    if ($value['required'] === True && empty($options[$key])) {
        $help = $value['help']; // 获取参数的帮助信息
        echo "Error: the following arguments are required: --$key, $help" . PHP_EOL;
        exit(1); // 如果必填参数缺失，则退出程序
    }
}

// 从解析的参数中提取值
$region = $options["region"]; // Bucket所在的地域
$bucket = $options["bucket"]; // Bucket名称
$key = $options["key"];       // 对象名称

// 加载环境变量中的凭证信息
// 使用EnvironmentVariableCredentialsProvider从环境变量中读取Access Key ID和Access Key Secret
$credentialsProvider = new Oss\Credentials\EnvironmentVariableCredentialsProvider();

// 使用SDK的默认配置
$cfg = Oss\Config::loadDefault();
$cfg->setCredentialsProvider($credentialsProvider); // 设置凭证提供者
$cfg->setRegion($region); // 设置Bucket所在的地域
if (isset($options["endpoint"])) {
    $cfg->setEndpoint($options["endpoint"]); // 如果提供了访问域名，则设置endpoint
}

// 创建OSS客户端实例
$client = new Oss\Client($cfg);

// 获取网络文件的内容
$url = 'https://www.aliyun.com/';
$response = file_get_contents($url);

// 创建PutObjectRequest对象，用于上传对象
$request = new Oss\Models\PutObjectRequest(bucket: $bucket, key: $key);
$request->body = Oss\Utils::streamFor($response); // 设置请求体为数据流

// 执行上传操作
$result = $client->putObject($request);

// 打印上传结果
printf(
    'status code: %s' . PHP_EOL . // HTTP状态码
    'request id: %s' . PHP_EOL .  // 请求ID
    'etag: %s' . PHP_EOL,         // 对象的ETag
    $result->statusCode,
    $result->requestId,
    $result->etag
);
```

在上传过程中实时展示上传进度。

Java

Go

PHP

.NET

Android

C++

iOS

C

使用前确保已 [配置访问凭证](https://help.aliyun.com/zh/oss/developer-reference/oss-java-sdk/#1aad0e2f2cft9) 并安装 [OSS Java SDK V1](https://help.aliyun.com/zh/oss/developer-reference/oss-java-sdk/) 。

更多信息，请参见 [Java上传进度条](https://help.aliyun.com/zh/oss/developer-reference/progress-bar-6) 。

```java
import com.aliyun.oss.*;
import com.aliyun.oss.common.auth.*;
import com.aliyun.oss.common.comm.SignVersion;
import com.aliyun.oss.event.ProgressEvent;
import com.aliyun.oss.event.ProgressEventType;
import com.aliyun.oss.event.ProgressListener;
import com.aliyun.oss.model.PutObjectRequest;
import java.io.File;

// 使用进度条，需要实现ProgressListener方法
public class PutObjectProgressListenerDemo implements ProgressListener {
    private long bytesWritten = 0;
    private long totalBytes = -1;
    private boolean succeed = false;

    public static void main(String[] args) throws Exception {
        // Endpoint以华东1（杭州）为例，其它Region请按实际情况填写。
        String endpoint = "https://oss-cn-hangzhou.aliyuncs.com";
        // 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
        EnvironmentVariableCredentialsProvider credentialsProvider = CredentialsProviderFactory.newEnvironmentVariableCredentialsProvider();
        // 填写Bucket名称，例如examplebucket。
        String bucketName = "examplebucket";
        // 填写Object完整路径，完整路径中不能包含Bucket名称。例如exampledir/exampleobject.txt。
        String objectName = "exampledir/exampleobject.txt";
        // 填写本地文件的完整路径，例如D:\\localpath\\examplefile.txt。
        String pathName = "D:\\localpath\\examplefile.txt";
        // 填写Bucket所在地域。以华东1（杭州）为例，Region填写为cn-hangzhou。
        String region = "cn-hangzhou";

        // 创建OSSClient实例。
        // 当OSSClient实例不再使用时，调用shutdown方法以释放资源。
        ClientBuilderConfiguration clientBuilderConfiguration = new ClientBuilderConfiguration();
        clientBuilderConfiguration.setSignatureVersion(SignVersion.V4);        
        OSS ossClient = OSSClientBuilder.create()
        .endpoint(endpoint)
        .credentialsProvider(credentialsProvider)
        .clientConfiguration(clientBuilderConfiguration)
        .region(region)               
        .build();

        try {
            // 上传文件的同时指定进度条参数。此处PutObjectProgressListenerDemo为调用类的类名，请在实际使用时替换为相应的类名。
            ossClient.putObject(new PutObjectRequest(bucketName,objectName, new File(pathName)).
                    <PutObjectRequest>withProgressListener(new PutObjectProgressListenerDemo()));
            // 下载文件的同时指定进度条参数。此处GetObjectProgressListenerDemo为调用类的类名，请在实际使用时替换为相应的类名。
//            ossClient.getObject(new GetObjectRequest(bucketName,objectName).
//                    <GetObjectRequest>withProgressListener(new GetObjectProgressListenerDemo()));

        } catch (OSSException oe) {
            System.out.println("Caught an OSSException, which means your request made it to OSS, "
                    + "but was rejected with an error response for some reason.");
            System.out.println("Error Message:" + oe.getErrorMessage());
            System.out.println("Error Code:" + oe.getErrorCode());
            System.out.println("Request ID:" + oe.getRequestId());
            System.out.println("Host ID:" + oe.getHostId());
        } catch (ClientException ce) {
            System.out.println("Caught an ClientException, which means the client encountered "
                    + "a serious internal problem while trying to communicate with OSS, "
                    + "such as not being able to access the network.");
            System.out.println("Error Message:" + ce.getMessage());
        } finally {
            if (ossClient != null) {
                ossClient.shutdown();
            }
        }
    }

    public boolean isSucceed() {
        return succeed;
    }

    // 使用进度条需要您重写回调方法，以下仅为参考示例。
    @Override
    public void progressChanged(ProgressEvent progressEvent) {
        long bytes = progressEvent.getBytes();
        ProgressEventType eventType = progressEvent.getEventType();
        switch (eventType) {
            case TRANSFER_STARTED_EVENT:
                System.out.println("Start to upload......");
                break;
            case REQUEST_CONTENT_LENGTH_EVENT:
                this.totalBytes = bytes;
                System.out.println(this.totalBytes + " bytes in total will be uploaded to OSS");
                break;
            case REQUEST_BYTE_TRANSFER_EVENT:
                this.bytesWritten += bytes;
                if (this.totalBytes != -1) {
                    int percent = (int)(this.bytesWritten * 100.0 / this.totalBytes);
                    System.out.println(bytes + " bytes have been written at this time, upload progress: " + percent + "%(" + this.bytesWritten + "/" + this.totalBytes + ")");
                } else {
                    System.out.println(bytes + " bytes have been written at this time, upload ratio: unknown" + "(" + this.bytesWritten + "/...)");
                }
                break;
            case TRANSFER_COMPLETED_EVENT:
                this.succeed = true;
                System.out.println("Succeed to upload, " + this.bytesWritten + " bytes have been transferred in total");
                break;
            case TRANSFER_FAILED_EVENT:
                System.out.println("Failed to upload, " + this.bytesWritten + " bytes have been transferred");
                break;
            default:
                break;
        }
    }
}
```

使用前确保已 [配置凭证](https://help.aliyun.com/zh/oss/quick-start-for-oss-go-sdk-v2#41f7244e024ul) 并 [安装OSS Go SDK](https://help.aliyun.com/zh/oss/quick-start-for-oss-go-sdk-v2#ff2e78dc863gg) 。

```
package main

import (
    "context"
    "flag"
    "fmt"
    "log"

    "github.com/aliyun/alibabacloud-oss-go-sdk-v2/oss"
    "github.com/aliyun/alibabacloud-oss-go-sdk-v2/oss/credentials"
)

// 定义全局变量
var (
    region     string // 存储区域
    bucketName string // 存储空间名称
    objectName string // 对象名称
)

// init函数用于初始化命令行参数
func init() {
    flag.StringVar(&region, "region", "", "The region in which the bucket is located.")
    flag.StringVar(&bucketName, "bucket", "", "The name of the bucket.")
    flag.StringVar(&objectName, "object", "", "The name of the object.")
}

func main() {
    // 解析命令行参数
    flag.Parse()

    // 检查bucket名称是否为空
    if len(bucketName) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, bucket name required")
    }

    // 检查region是否为空
    if len(region) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, region required")
    }

    // 检查object名称是否为空
    if len(objectName) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, object name required")
    }

    // 加载默认配置并设置凭证提供者和区域
    cfg := oss.LoadDefaultConfig().
        WithCredentialsProvider(credentials.NewEnvironmentVariableCredentialsProvider()).
        WithRegion(region)

    // 创建OSS客户端
    client := oss.NewClient(cfg)

    // 填写要上传的本地文件路径和文件名称，例如 /Users/localpath/exampleobject.txt
    localFile := "/Users/localpath/exampleobject.txt"

    // 创建上传对象的请求
    putRequest := &oss.PutObjectRequest{
        Bucket: oss.Ptr(bucketName), // 存储空间名称
        Key:    oss.Ptr(objectName), // 对象名称
        ProgressFn: func(increment, transferred, total int64) {
            fmt.Printf("increment:%v, transferred:%v, total:%v\n", increment, transferred, total)
        }, // 进度回调函数，用于显示上传进度
    }

    // 发送上传对象的请求
    result, err := client.PutObjectFromFile(context.TODO(), putRequest, localFile)
    if err != nil {
        log.Fatalf("failed to put object from file %v", err)
    }

    // 打印上传对象的结果
    log.Printf("put object from file result:%#v\n", result)
}
```

```php
<?php

// 引入自动加载文件，确保依赖库能够正确加载
require_once __DIR__ . '/../vendor/autoload.php';

use AlibabaCloud\Oss\V2 as Oss;

// 定义命令行参数的描述信息
$optsdesc = [
    "region" => ['help' => 'The region in which the bucket is located.', 'required' => True], // Bucket 所在的地域（必填）
    "endpoint" => ['help' => 'The domain names that other services can use to access OSS.', 'required' => False], // 访问域名（可选）
    "bucket" => ['help' => 'The name of the bucket', 'required' => True], // Bucket 名称（必填）
    "key" => ['help' => 'The name of the object', 'required' => True], // 对象名称（必填）
];

// 将参数描述转换为 getopt 所需的长选项格式
// 每个参数后面加上 ":" 表示该参数需要值
$longopts = \array_map(function ($key) {
    return "$key:";
}, array_keys($optsdesc));

// 解析命令行参数
$options = getopt("", $longopts);

// 验证必填参数是否存在
foreach ($optsdesc as $key => $value) {
    if ($value['required'] === True && empty($options[$key])) {
        $help = $value['help']; // 获取参数的帮助信息
        echo "Error: the following arguments are required: --$key, $help";
        exit(1); // 如果必填参数缺失，则退出程序
    }
}

// 从解析的参数中提取值
$region = $options["region"]; // Bucket 所在的地域
$bucket = $options["bucket"]; // Bucket 名称
$key = $options["key"];       // 对象名称

// 使用 EnvironmentVariableCredentialsProvider 从环境变量中加载访问凭证
// 确保环境变量 ALIBABA_CLOUD_ACCESS_KEY_ID 和 ALIBABA_CLOUD_ACCESS_KEY_SECRET 已正确设置
$credentialsProvider = new Oss\Credentials\EnvironmentVariableCredentialsProvider();

// 加载 SDK 的默认配置
$cfg = Oss\Config::loadDefault();
$cfg->setCredentialsProvider($credentialsProvider); // 设置凭证提供者
$cfg->setRegion($region); // 设置 Bucket 所在的地域

// 如果命令行提供了 endpoint 参数，则使用指定的访问域名
if (isset($options["endpoint"])) {
    $cfg->setEndpoint($options["endpoint"]);
}

// 创建 OSS 客户端实例
$client = new Oss\Client($cfg);

// 定义要上传的数据内容
$data = 'Hello OSS';

// 创建 PutObjectRequest 对象，指定 Bucket 和对象 Key
$request = new Oss\Models\PutObjectRequest($bucket, $key);

// 将数据内容转换为流对象
$request->body = Oss\Utils::streamFor($data);

// 设置上传进度回调函数
$request->progressFn = function (int $increment, int $transferred, int $total) {
    echo sprintf("已经上传：%d" . PHP_EOL, $transferred); // 当前已上传的字节数
    echo sprintf("本次上传：%d" . PHP_EOL, $increment);   // 本次上传的字节数增量
    echo sprintf("数据总共：%d" . PHP_EOL, $total);       // 数据总大小
    echo '-------------------------------------------' . PHP_EOL; // 分隔线
};

// 调用 putObject 方法上传对象
$result = $client->putObject($request);

// 输出上传结果
printf(
    'status code: %s' . PHP_EOL, $result->statusCode . // HTTP 响应状态码
    'request id: %s' . PHP_EOL, $result->requestId .   // 请求 ID
    'etag: %s' . PHP_EOL, $result->etag                // 对象的 ETag
);
```

```csharp
using System;
using System.IO;
using System.Text;
using Aliyun.OSS;
using Aliyun.OSS.Common;
namespace PutObjectProgress
{
    class Program
    {
        static void Main(string[] args)
        {
            Program.PutObjectProgress();
            Console.ReadKey();
        }
        public static void PutObjectProgress()
        {
            // yourEndpoint填写Bucket所在地域对应的Endpoint。以华东1（杭州）为例，Endpoint填写为https://oss-cn-hangzhou.aliyuncs.com。
            var endpoint = "yourEndpoint";
            // 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
            var accessKeyId = Environment.GetEnvironmentVariable("OSS_ACCESS_KEY_ID");
            var accessKeySecret = Environment.GetEnvironmentVariable("OSS_ACCESS_KEY_SECRET");
            // 填写Bucket名称。
            var bucketName = "yourBucketName";
            // 填写不包含Bucket名称在内的Object的完整路径。
            var objectName = "yourObjectName";
            // 填写本地文件的完整路径。例如，本地文件examplefile.txt存储于本地D盘的localpath路径下，则此处填写为D:\\localpath\\examplefile.txt。
            var localFilename = "yourLocalFilename";
            // 填写Bucket所在地域对应的Region。以华东1（杭州）为例，Region填写为cn-hangzhou。
            const string region = "cn-hangzhou";
            // 创建ClientConfiguration实例，按照您的需要修改默认参数。
            var conf = new ClientConfiguration();
            // 设置v4签名。
            conf.SignatureVersion = SignatureVersion.V4;

            // 创建OssClient实例。
            var client = new OssClient(endpoint, accessKeyId, accessKeySecret, conf);
            client.SetRegion(region);
            // 带进度条的上传。
            try
            {
                using (var fs = File.Open(localFilename, FileMode.Open))
                {
                    var putObjectRequest = new PutObjectRequest(bucketName, objectName, fs);
                    putObjectRequest.StreamTransferProgress += streamProgressCallback;
                    client.PutObject(putObjectRequest);
                }
                Console.WriteLine("Put object:{0} succeeded", objectName);
            }
            catch (OssException ex)
            {
                Console.WriteLine("Failed with error code: {0}; Error info: {1}. \nRequestID: {2}\tHostID: {3}",
                    ex.ErrorCode, ex.Message, ex.RequestId, ex.HostId);
            }
            catch (Exception ex)
            {
                Console.WriteLine("Failed with error info: {0}", ex.Message);
            }
        }
        // 获取上传进度。
        private static void streamProgressCallback(object sender, StreamTransferProgressArgs args)
        {
            System.Console.WriteLine("ProgressCallback - Progress: {0}%, TotalBytes:{1}, TransferredBytes:{2} ",
                args.TransferredBytes * 100 / args.TotalBytes, args.TotalBytes, args.TransferredBytes);
        }
    }
}
```

```
// 构造上传请求。
// 依次填写Bucket名称（例如examplebucket）、Object完整路径（例如exampledir/exampleobject.txt）和本地文件完整路径（例如/storage/emulated/0/oss/examplefile.txt）。
// Object完整路径中不能包含Bucket名称。
PutObjectRequest put = new PutObjectRequest("examplebucket", "exampledir/exampleobject.txt", "/storage/emulated/0/oss/examplefile.txt");

// 设置进度回调函数打印进度条。
put.setProgressCallback(new OSSProgressCallback<PutObjectRequest>() {
    @Override
    public void onProgress(PutObjectRequest request, long currentSize, long totalSize) {
        // currentSize表示已上传文件的大小，单位为字节。
        // totalSize表示上传文件的总大小，单位为字节。
        Log.d("PutObject", "currentSize: " + currentSize + " totalSize: " + totalSize);
    }
});

// 异步上传。
OSSAsyncTask task = oss.asyncPutObject(put, new OSSCompletedCallback<PutObjectRequest, PutObjectResult>() {
    @Override
    public void onSuccess(PutObjectRequest request, PutObjectResult result) {
        Log.d("PutObject", "UploadSuccess");
        Log.d("ETag", result.getETag());
        Log.d("RequestId", result.getRequestId());
    }

    @Override
    public void onFailure(PutObjectRequest request, ClientException clientExcepion, ServiceException serviceException) {
        // 请求异常。
        if (clientExcepion != null) {
            // 本地异常，如网络异常等。
            clientExcepion.printStackTrace();
        }
        if (serviceException != null) {
            // 服务异常。
            Log.e("ErrorCode", serviceException.getErrorCode());
            Log.e("RequestId", serviceException.getRequestId());
            Log.e("HostId", serviceException.getHostId());
            Log.e("RawMessage", serviceException.getRawMessage());
        }
    }
});
// task.cancel(); // 可以取消任务。
// task.waitUntilFinished(); // 等待任务完成。
```

```c
#include <alibabacloud/oss/OssClient.h>
#include <fstream>
using namespace AlibabaCloud::OSS;

void ProgressCallback(size_t increment, int64_t transfered, int64_t total, void* userData)
{
    // increment表示本次回调发送的数据大小。
    // transfered表示已上传的数据大小。
    // total表示上传文件的总大小。
    std::cout << "ProgressCallback[" << userData << "] => " <<
    increment <<" ," << transfered << "," << total << std::endl;
}

int main(void)
{
    /* 初始化OSS账号信息。*/
            
    /* yourEndpoint填写Bucket所在地域对应的Endpoint。以华东1（杭州）为例，Endpoint填写为https://oss-cn-hangzhou.aliyuncs.com。*/
    std::string Endpoint = "yourEndpoint";
    / *yourRegion填写Bucket所在地域对应的Region。以华东1（杭州）为例，Region填写为cn - hangzhou。 * /
    std::string Region = "yourRegion";
    /* 填写Bucket名称，例如examplebucket。*/
    std::string BucketName = "examplebucket";
    /* 填写Object完整路径，完整路径中不能包含Bucket名称，例如exampledir/exampleobject.txt。*/
    std::string ObjectName = "exampledir/exampleobject.txt";

    /* 初始化网络等资源。*/
    InitializeSdk();

    ClientConfiguration conf;
    conf.signatureVersion = SignatureVersionType::V4;
    /* 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。*/
    auto credentialsProvider = std::make_shared<EnvironmentVariableCredentialsProvider>();
    OssClient client(Endpoint, credentialsProvider, conf);
    client.SetRegion(Region);
  
    /* yourLocalFilename填写本地文件完整路径。*/
    std::shared_ptr<std::iostream> content = std::make_shared<std::fstream>("yourLocalFilename", std::ios::in|std::ios::binary);
    PutObjectRequest request(BucketName, ObjectName, content);
  
    TransferProgress progressCallback = { ProgressCallback , nullptr };
    request.setTransferProgress(progressCallback);
   
    /* 上传文件。*/
    auto outcome = client.PutObject(request);

    if (!outcome.isSuccess()) {
        /* 异常处理。*/
        std::cout << "PutObject fail" <<
        ",code:" << outcome.error().Code() <<
        ",message:" << outcome.error().Message() <<
        ",requestId:" << outcome.error().RequestId() << std::endl;
        return -1;
    }

    /* 释放网络等资源。*/
    ShutdownSdk();
    return 0;
}
```

```
OSSPutObjectRequest * put = [OSSPutObjectRequest new];
// 填写Bucket名称，例如examplebucket。
put.bucketName = @"examplebucket";
// 填写Object完整路径，完整路径中不能包含Bucket名称，例如exampledir/exampleobject.txt。
put.objectKey = @"exampledir/exampleobject.txt";
// 填写本地文件的完整路径。
// 如果未指定本地路径，则默认从示例程序所属项目对应本地路径中上传文件。
put.uploadingFileURL = [NSURL fileURLWithPath:@"filePath"];
// 设置进度回调函数打印进度条。
put.uploadProgress = ^(int64_t bytesSent, int64_t totalByteSent, int64_t totalBytesExpectedToSend) {
    // 当前上传长度、当前已上传总长度、待上传的总长度。
    NSLog(@"%lld, %lld, %lld", bytesSent, totalByteSent, totalBytesExpectedToSend);
};
OSSTask * putTask = [client putObject:put];
[putTask continueWithBlock:^id(OSSTask *task) {
    if (!task.error) {
        NSLog(@"upload object success!");
    } else {
        NSLog(@"upload object failed, error: %@" , task.error);
    }
    return nil;
}];
// 实现同步阻塞等待任务完成。
// [putTask waitUntilFinished];
```

```c
#include "oss_api.h"
#include "aos_http_io.h"
/* yourEndpoint填写Bucket所在地域对应的Endpoint。以华东1（杭州）为例，Endpoint填写为https://oss-cn-hangzhou.aliyuncs.com。*/
const char *endpoint = "yourEndpoint";

/* 填写Bucket名称，例如examplebucket。*/
const char *bucket_name = "examplebucket";
/* 填写Object完整路径，完整路径中不能包含Bucket名称，例如exampledir/exampleobject.txt。*/
const char *object_name = "exampledir/exampleobject.txt";
/* 填写本地文件的完整路径。*/
const char *local_filename = "yourLocalFilename";
/* yourRegion填写Bucket所在地域对应的Region。以华东1（杭州）为例，Region填写为cn-hangzhou。*/
const char *region = "yourRegion";
void init_options(oss_request_options_t *options)
{
    options->config = oss_config_create(options->pool);
    /* 用char*类型的字符串初始化aos_string_t类型。*/
    aos_str_set(&options->config->endpoint, endpoint);
    /* 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。*/    
    aos_str_set(&options->config->access_key_id, getenv("OSS_ACCESS_KEY_ID"));
    aos_str_set(&options->config->access_key_secret, getenv("OSS_ACCESS_KEY_SECRET"));
    //需要额外配置以下两个参数
    aos_str_set(&options->config->region, region);
    options->config->signature_version = 4;
    /* 是否使用了CNAME。0表示不使用。*/
    options->config->is_cname = 0;
    /* 设置网络相关参数，比如超时时间等。*/
    options->ctl = aos_http_controller_create(options->pool, 0);
}
void percentage(int64_t consumed_bytes, int64_t total_bytes) 
{
    assert(total_bytes >= consumed_bytes);
    printf("%%%" APR_INT64_T_FMT "\n", consumed_bytes * 100 / total_bytes);
}
int main(int argc, char *argv[])
{
    /* 在程序入口调用aos_http_io_initialize方法来初始化网络、内存等全局资源。*/
    if (aos_http_io_initialize(NULL, 0) != AOSE_OK) {
        exit(1);
    }
    /* 用于内存管理的内存池（pool），等价于apr_pool_t。其实现代码在apr库中。*/
    aos_pool_t *pool;
    /* 重新创建一个内存池，第二个参数是NULL，表示没有继承其它内存池。*/
    aos_pool_create(&pool, NULL);
    /* 创建并初始化options，该参数包括endpoint、access_key_id、acces_key_secret、is_cname、curl等全局配置信息。*/
    oss_request_options_t *oss_client_options;
    /* 在内存池中分配内存给options。*/
    oss_client_options = oss_request_options_create(pool);
    /* 初始化Client的选项oss_client_options。*/
    init_options(oss_client_options);
    /* 初始化参数。*/
    aos_string_t bucket;
    aos_string_t object;
    aos_string_t file;   
    aos_list_t resp_body;
    aos_table_t *resp_headers = NULL;
    aos_status_t *resp_status = NULL; 
    aos_str_set(&bucket, bucket_name);
    aos_str_set(&object, object_name);
    aos_str_set(&file, local_filename);
    /* 带进度条的上传。*/
    resp_status = oss_do_put_object_from_file(oss_client_options, &bucket, &object, &file, NULL, NULL, percentage, &resp_headers, &resp_body);
    if (aos_status_is_ok(resp_status)) {
        printf("put object from file succeeded\n");
    } else {
        printf("put object from file failed\n");
    }
    /* 释放内存池，相当于释放了请求过程中各资源分配的内存。*/
    aos_pool_destroy(pool);
    /* 释放之前分配的全局资源。*/
    aos_http_io_deinitialize();
    return 0;
}
```

在文件上传完成后，通过回调通知应用服务器进行后续处理。更多回调原理信息，请参见 [Callback](https://help.aliyun.com/zh/oss/developer-reference/callback) 。

Java

Python

Go

PHP

.NET

Node.js

Ruby

Browser.js

Android

C++

iOS

C

使用前确保已 [配置访问凭证](https://help.aliyun.com/zh/oss/developer-reference/oss-java-sdk/#1aad0e2f2cft9) 并安装 [OSS Java SDK V1](https://help.aliyun.com/zh/oss/developer-reference/oss-java-sdk/) 。

```java
import com.aliyun.oss.ClientBuilderConfiguration;
import com.aliyun.oss.OSS;
import com.aliyun.oss.OSSClientBuilder;
import com.aliyun.oss.OSSException;
import com.aliyun.oss.common.auth.CredentialsProviderFactory;
import com.aliyun.oss.common.auth.EnvironmentVariableCredentialsProvider;
import com.aliyun.oss.common.comm.SignVersion;
import com.aliyun.oss.model.Callback;
import com.aliyun.oss.model.PutObjectRequest;
import com.aliyun.oss.model.PutObjectResult;

import java.io.ByteArrayInputStream;

public class Demo {

    public static void main(String[] args) throws Exception{
        // Endpoint以华东1（杭州）为例，其它Region请按实际情况填写。
        String endpoint = "https://oss-cn-hangzhou.aliyuncs.com";
        // 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
        EnvironmentVariableCredentialsProvider credentialsProvider = CredentialsProviderFactory.newEnvironmentVariableCredentialsProvider();
        // 填写Bucket名称，例如examplebucket。
        String bucketName = "examplebucket";
        // 填写Object完整路径，例如exampledir/exampleobject.txt。Object完整路径中不能包含Bucket名称。
        String objectName = "exampledir/exampleobject.txt";
        // 您的回调服务器地址，例如https://example.com:23450。
        String callbackUrl = "yourCallbackServerUrl";
        // 填写Bucket所在地域。以华东1（杭州）为例，Region填写为cn-hangzhou。
        String region = "cn-hangzhou";

        // 创建OSSClient实例。
        // 当OSSClient实例不再使用时，调用shutdown方法以释放资源。
        ClientBuilderConfiguration clientBuilderConfiguration = new ClientBuilderConfiguration();
        clientBuilderConfiguration.setSignatureVersion(SignVersion.V4);        
        OSS ossClient = OSSClientBuilder.create()
        .endpoint(endpoint)
        .credentialsProvider(credentialsProvider)
        .clientConfiguration(clientBuilderConfiguration)
        .region(region)               
        .build();
        
        try {
            String content = "Hello OSS";
            PutObjectRequest putObjectRequest = new PutObjectRequest(bucketName, objectName,new ByteArrayInputStream(content.getBytes()));

            // 配置上传回调参数
            Callback callback = new Callback();
            callback.setCallbackUrl(callbackUrl);
            //（可选）设置回调请求消息头中Host的值，即您的服务器配置Host的值。
            // callback.setCallbackHost("yourCallbackHost");
            
            // 设置回调请求的 Body 内容，采用 JSON 格式，并在其中定义占位符变量。
            callback.setCalbackBodyType(Callback.CalbackBodyType.JSON);
            callback.setCallbackBody("{\\\"bucket\\\":${bucket},\\\"object\\\":${object},\\\"mimeType\\\":${mimeType},\\\"size\\\":${size},\\\"my_var1\\\":${x:var1},\\\"my_var2\\\":${x:var2}}");

            // 设置发起回调请求的自定义参数，由Key和Value组成，Key必须以x:开始。
            callback.addCallbackVar("x:var1", "value1");
            callback.addCallbackVar("x:var2", "value2");
            putObjectRequest.setCallback(callback);

            // 执行上传操作
            PutObjectResult putObjectResult = ossClient.putObject(putObjectRequest);

            // 读取上传回调返回的消息内容。
            byte[] buffer = new byte[1024];
            putObjectResult.getResponse().getContent().read(buffer);
            // 数据读取完成后，获取的流必须关闭，否则会造成连接泄漏，导致请求无连接可用，程序无法正常工作。
            putObjectResult.getResponse().getContent().close();
        } catch (OSSException oe) {
            System.out.println("Caught an OSSException, which means your request made it to OSS, "
                    + "but was rejected with an error response for some reason.");
            System.out.println("Error Message:" + oe.getErrorMessage());
            System.out.println("Error Code:" + oe.getErrorCode());
            System.out.println("Request ID:" + oe.getRequestId());
            System.out.println("Host ID:" + oe.getHostId());
        } catch (Throwable ce) {
            System.out.println("Caught an ClientException, which means the client encountered "
                    + "a serious internal problem while trying to communicate with OSS, "
                    + "such as not being able to access the network.");
            System.out.println("Error Message:" + ce.getMessage());
        } finally {
            if (ossClient != null) {
                ossClient.shutdown();
            }
        }
    }
}
```

使用前确保已 [配置凭证](https://help.aliyun.com/zh/oss/get-started-with-oss-sdk-for-python-v2#745a317b4ci01) 并 [安装OSS Python SDK](https://help.aliyun.com/zh/oss/get-started-with-oss-sdk-for-python-v2#addadb57a9xyy) 。

```python
import base64
import argparse
import alibabacloud_oss_v2 as oss

parser = argparse.ArgumentParser(description="put object sample")

# 添加必要的参数
parser.add_argument('--region', help='The region in which the bucket is located.', required=True)
parser.add_argument('--bucket', help='The name of the bucket.', required=True)
parser.add_argument('--endpoint', help='The domain names that other services can use to access OSS')
parser.add_argument('--key', help='The name of the object.', required=True)
parser.add_argument('--call_back_url', help='Callback server address.', required=True)

def main():

    args = parser.parse_args()

    # 从环境变量中加载凭证信息
    credentials_provider = oss.credentials.EnvironmentVariableCredentialsProvider()

    # 配置 SDK 客户端
    cfg = oss.config.load_default()
    cfg.credentials_provider = credentials_provider
    cfg.region = args.region
    if args.endpoint is not None:
        cfg.endpoint = args.endpoint

    # 创建 OSS 客户端
    client = oss.Client(cfg)

    # 要上传的内容（字符串）
    data = 'hello world'

    # 构造回调参数（callback）：指定回调地址和回调请求体，使用 Base64 编码
    callback=base64.b64encode(str('{\"callbackUrl\":\"' + args.call_back_url + '\",\"callbackBody\":\"bucket=${bucket}&object=${object}&my_var_1=${x:var1}&my_var_2=${x:var2}\"}').encode()).decode()
    # 构造自定义变量（callback-var），使用 Base64 编码
    callback_var=base64.b64encode('{\"x:var1\":\"value1\",\"x:var2\":\"value2\"}'.encode()).decode()

    # 发起上传请求，并携带回调参数
    result = client.put_object(oss.PutObjectRequest(
        bucket=args.bucket,
        key=args.key,
        body=data,
        callback=callback,
        callback_var=callback_var,
    ))
    # 打印返回结果（包括状态码、请求 ID 等）
    print(vars(result))

if __name__ == "__main__":
    main()
```

使用前确保已 [配置凭证](https://help.aliyun.com/zh/oss/quick-start-for-oss-go-sdk-v2#41f7244e024ul) 并 [安装OSS Go SDK](https://help.aliyun.com/zh/oss/quick-start-for-oss-go-sdk-v2#ff2e78dc863gg) 。

```
package main

import (
    "context"
    "encoding/base64"
    "encoding/json"
    "flag"
    "log"
    "strings"

    "github.com/aliyun/alibabacloud-oss-go-sdk-v2/oss"
    "github.com/aliyun/alibabacloud-oss-go-sdk-v2/oss/credentials"
)

// 定义全局变量
var (
    region     string // 存储区域
    bucketName string // 存储空间名称
    objectName string // 对象名称
)

// init函数用于初始化命令行参数
func init() {
    flag.StringVar(&region, "region", "", "The region in which the bucket is located.")
    flag.StringVar(&bucketName, "bucket", "", "The name of the bucket.")
    flag.StringVar(&objectName, "object", "", "The name of the object.")
}

func main() {
    // 解析命令行参数
    flag.Parse()

    // 检查bucket名称是否为空
    if len(bucketName) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, bucket name required")
    }

    // 检查region是否为空
    if len(region) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, region required")
    }

    // 检查object名称是否为空
    if len(objectName) == 0 {
        flag.PrintDefaults()
        log.Fatalf("invalid parameters, object name required")
    }

    // 加载默认配置并设置凭证提供者和区域
    cfg := oss.LoadDefaultConfig().
        WithCredentialsProvider(credentials.NewEnvironmentVariableCredentialsProvider()).
        WithRegion(region)

    // 创建OSS客户端
    client := oss.NewClient(cfg)

    // 定义回调参数
    callbackMap := map[string]string{
        "callbackUrl":      "http://example.com:23450",                                                        // 设置回调服务器的URL，例如https://example.com:23450。
        "callbackBody":     "bucket=${bucket}&object=${object}&size=${size}&my_var_1=${x:my_var1}&my_var_2=${x:my_var2}", // 设置回调请求体。
        "callbackBodyType": "application/x-www-form-urlencoded",                                                          //设置回调请求体类型。
    }

    // 将回调参数转换为JSON并进行Base64编码，以便将其作为回调参数传递
    callbackStr, err := json.Marshal(callbackMap)
    if err != nil {
        log.Fatalf("failed to marshal callback map: %v", err)
    }
    callbackBase64 := base64.StdEncoding.EncodeToString(callbackStr)

    callbackVarMap := map[string]string{}
    callbackVarMap["x:my_var1"] = "thi is var 1"
    callbackVarMap["x:my_var2"] = "thi is var 2"
    callbackVarStr, err := json.Marshal(callbackVarMap)
    if err != nil {
        log.Fatalf("failed to marshal callback var: %v", err)
    }
    callbackVarBase64 := base64.StdEncoding.EncodeToString(callbackVarStr)
    // 定义要上传的字符串内容
    body := strings.NewReader("Hello, OSS!") // 替换为要上传的字符串内容

    // 创建上传对象的请求
    request := &oss.PutObjectRequest{
        Bucket:      oss.Ptr(bucketName),     // 存储空间名称
        Key:         oss.Ptr(objectName),     // 对象名称
        Body:        body,                    // 对象内容
        Callback:    oss.Ptr(callbackBase64), // 填写回调参数
        CallbackVar: oss.Ptr(callbackVarBase64),
    }

    // 发送上传对象的请求
    result, err := client.PutObject(context.TODO(), request)
    if err != nil {
        log.Fatalf("failed to put object %v", err)
    }

    // 打印上传对象的结果
    log.Printf("put object result:%#v\n", result)
}
```

```php
<?php

// 引入自动加载文件，确保依赖库能够正确加载
require_once __DIR__ . '/../vendor/autoload.php';

use AlibabaCloud\Oss\V2 as Oss;

// 定义命令行参数的描述信息
$optsdesc = [
    "region" => ['help' => 'The region in which the bucket is located.', 'required' => True], // Bucket所在的地域（必填）
    "endpoint" => ['help' => 'The domain names that other services can use to access OSS.', 'required' => False], // 访问域名（可选）
    "bucket" => ['help' => 'The name of the bucket', 'required' => True], // Bucket名称（必填）
    "key" => ['help' => 'The name of the object', 'required' => True], // 对象名称（必填）
];

// 将参数描述转换为getopt所需的长选项格式
// 每个参数后面加上":"表示该参数需要值
$longopts = \array_map(function ($key) {
    return "$key:";
}, array_keys($optsdesc));

// 解析命令行参数
$options = getopt("", $longopts);

// 验证必填参数是否存在
foreach ($optsdesc as $key => $value) {
    if ($value['required'] === True && empty($options[$key])) {
        $help = $value['help']; // 获取参数的帮助信息
        echo "Error: the following arguments are required: --$key, $help" . PHP_EOL;
        exit(1); // 如果必填参数缺失，则退出程序
    }
}

// 从解析的参数中提取值
$region = $options["region"]; // Bucket所在的地域
$bucket = $options["bucket"]; // Bucket名称
$key = $options["key"];       // 对象名称

// 加载环境变量中的凭证信息
// 使用EnvironmentVariableCredentialsProvider从环境变量中读取Access Key ID和Access Key Secret
$credentialsProvider = new Oss\Credentials\EnvironmentVariableCredentialsProvider();

// 使用SDK的默认配置
$cfg = Oss\Config::loadDefault();
$cfg->setCredentialsProvider($credentialsProvider); // 设置凭证提供者
$cfg->setRegion($region); // 设置Bucket所在的地域
if (isset($options["endpoint"])) {
    $cfg->setEndpoint($options["endpoint"]); // 如果提供了访问域名，则设置endpoint
}

// 创建OSS客户端实例
$client = new Oss\Client($cfg);

// 定义回调服务器的相关信息
// 回调URL：接收回调请求的服务器地址
// 回调Host：回调服务器的主机名
// 回调Body：定义回调内容的模板，支持动态占位符替换
// 回调BodyType：指定回调内容的格式
$callback = base64_encode(json_encode(array(
    'callbackUrl' => 'yourCallbackServerUrl', // 替换为实际的回调服务器URL
    'callbackHost' => 'yourCallbackServerHost', // 替换为实际的回调服务器主机名
    'callbackBody' => 'bucket=${bucket}&object=${object}&etag=${etag}&size=${size}&mimeType=${mimeType}&imageInfo.height=${imageInfo.height}&imageInfo.width=${imageInfo.width}&imageInfo.format=${imageInfo.format}&my_var1=${x:var1}&my_var2=${x:var2}',
    'callbackBodyType' => "application/x-www-form-urlencoded", // 回调内容的格式
)));

// 定义自定义变量，用于在回调中传递额外信息
$callbackVar = base64_encode(json_encode(array(
    'x:var1' => "value1", // 自定义变量1
    'x:var2' => 'value2', // 自定义变量2
)));

// 创建PutObjectRequest对象，用于上传对象
$request = new Oss\Models\PutObjectRequest(bucket: $bucket, key: $key);
$request->callback = $callback; // 设置回调信息
$request->callbackVar = $callbackVar; // 设置自定义变量

// 执行上传操作
$result = $client->putObject($request);

// 打印上传结果
// 输出HTTP状态码、请求ID以及回调结果，用于验证上传是否成功
printf(
    'status code:' . $result->statusCode . PHP_EOL . // HTTP状态码，例如200表示成功
    'request id:' . $result->requestId . PHP_EOL .   // 请求ID，用于调试或追踪请求
    'callback result:' . var_export($result->callbackResult, true) . PHP_EOL // 回调结果的详细信息
);
```

```csharp
using System;
using System.IO;
using System.Text;
using Aliyun.OSS;
using Aliyun.OSS.Common;
using Aliyun.OSS.Util;
namespace Callback
{
    class Program
    {
        static void Main(string[] args)
        {
            Program.PutObjectCallback();
            Console.ReadKey();
        }
        public static void PutObjectCallback()
        {
            // 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
            var accessKeyId = Environment.GetEnvironmentVariable("OSS_ACCESS_KEY_ID");
            var accessKeySecret = Environment.GetEnvironmentVariable("OSS_ACCESS_KEY_SECRET");
            // 填写Bucket名称，例如examplebucket。
            var bucketName = "examplebucket";
            // 填写Object完整路径。Object完整路径中不能包含Bucket名称，例如exampledir/exampleobject.txt。
            var objectName = "exampledir/exampleobject.txt";
           // 填写本地文件的完整路径，例如D:\\localpath\\examplefile.txt。如果未指定本地路径，则默认从示例程序所属项目对应本地路径中上传文件。
            var localFilename = "D:\\localpath\\examplefile.txt";
            // 设置回调服务器地址，例如https://example.com:23450。
            const string callbackUrl = "yourCallbackServerUrl";
            // 设置发起回调时请求body的值。
            const string callbackBody = "bucket=${bucket}&object=${object}&etag=${etag}&size=${size}&mimeType=${mimeType}&" +
                                        "my_var1=${x:var1}&my_var2=${x:var2}";
            //  填写Bucket所在地域对应的Endpoint。以华东1（杭州）为例，Endpoint填写为https://oss-cn-hangzhou.aliyuncs.com。
            const string endpoint = "https://oss-cn-hangzhou.aliyuncs.com";
            // 填写Bucket所在地域对应的Region。以华东1（杭州）为例，Region填写为cn-hangzhou。
            const string region = "cn-hangzhou";
            // 创建ClientConfiguration实例，按照您的需要修改默认参数。
            var conf = new ClientConfiguration();
            // 设置v4签名。
            conf.SignatureVersion = SignatureVersion.V4;

            // 创建OssClient实例。
            var client = new OssClient(endpoint, accessKeyId, accessKeySecret, conf);
            client.SetRegion(region);
            try
            {
                string responseContent = "";
                var metadata = BuildCallbackMetadata(callbackUrl, callbackBody);
                using (var fs = File.Open(localFilename, FileMode.Open))
                {
                    var putObjectRequest = new PutObjectRequest(bucketName, objectName, fs, metadata);
                    var result = client.PutObject(putObjectRequest);
                    responseContent = GetCallbackResponse(result);
                }
                Console.WriteLine("Put object:{0} succeeded, callback response content:{1}", objectName, responseContent);
            }
            catch (OssException ex)
            {
                Console.WriteLine("Failed with error code: {0}; Error info: {1}. \nRequestID: {2}\tHostID: {3}",
                    ex.ErrorCode, ex.Message, ex.RequestId, ex.HostId);
            }
            catch (Exception ex)
            {
                Console.WriteLine("Failed with error info: {0}", ex.Message);
            }
        }
        // 设置上传回调。
        private static ObjectMetadata BuildCallbackMetadata(string callbackUrl, string callbackBody)
        {
            string callbackHeaderBuilder = new CallbackHeaderBuilder(callbackUrl, callbackBody).Build();
            string CallbackVariableHeaderBuilder = new CallbackVariableHeaderBuilder().
                AddCallbackVariable("x:var1", "x:value1").AddCallbackVariable("x:var2", "x:value2").Build();
            var metadata = new ObjectMetadata();
            metadata.AddHeader(HttpHeaders.Callback, callbackHeaderBuilder);
            metadata.AddHeader(HttpHeaders.CallbackVar, CallbackVariableHeaderBuilder);
            return metadata;
        }
        // 读取上传回调返回的消息内容。
        private static string GetCallbackResponse(PutObjectResult putObjectResult)
        {
            string callbackResponse = null;
            using (var stream = putObjectResult.ResponseStream)
            {
                var buffer = new byte[4 * 1024];
                var bytesRead = stream.Read(buffer, 0, buffer.Length);
                callbackResponse = Encoding.Default.GetString(buffer, 0, bytesRead);
            }
            return callbackResponse;
        }
    }
}
```

```
const OSS = require("ali-oss");

var path = require("path");

const client = new OSS({
  // yourregion填写Bucket所在地域。以华东1（杭州）为例，Region填写为oss-cn-hangzhou。
  region: "yourregion",
  // 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
  accessKeyId: process.env.OSS_ACCESS_KEY_ID,
  accessKeySecret: process.env.OSS_ACCESS_KEY_SECRET,
  authorizationV4: true,
  // 填写Bucket名称。
  bucket: "examplebucket",
});

const options = {
  callback: {
    // 设置回调请求的服务器地址，例如http://oss-demo.aliyuncs.com:23450。
    url: "http://oss-demo.aliyuncs.com:23450",
    //（可选）设置回调请求消息头中Host的值，即您的服务器配置Host的值。
    //host: 'yourCallbackHost',
    // 设置发起回调时请求body的值。
    body: "bucket=${bucket}&object=${object}&var1=${x:var1}&var2=${x:var2}",
    // 设置发起回调请求的Content-Type。
    contentType: "application/x-www-form-urlencoded",
    // 客户端发起回调请求时，OSS是否向通过callbackUrl指定的回源地址发送服务器名称指示SNI（Server Name Indication）
    callbackSNI: true,
    // 设置发起回调请求的自定义参数。
    customValue: {
      var1: "value1",
      var2: "value2",
    },
  },
};

async function put() {
  try {
    // 填写Object完整路径和本地文件的完整路径。Object完整路径中不能包含Bucket名称。
    // 如果未指定本地路径，则默认从示例程序所属项目对应本地路径中上传文件。
    let result = await client.put(
      "exampleobject.txt",
      path.normalize("/localpath/examplefile.txt"),
      options
    );
    console.log(result);
  } catch (e) {
    console.log(e);
  }
}

put();
```

```ruby
require 'aliyun/oss'

client = Aliyun::OSS::Client.new(
  # Endpoint以华东1（杭州）为例，其它Region请按实际情况填写。
  endpoint: 'https://oss-cn-hangzhou.aliyuncs.com',
    # 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
  access_key_id: ENV['OSS_ACCESS_KEY_ID'],
  access_key_secret: ENV['OSS_ACCESS_KEY_SECRET']
)
# 填写Bucket名称，例如examplebucket。
bucket = client.get_bucket('examplebucket')

callback = Aliyun::OSS::Callback.new(
  url: 'http://oss-demo.aliyuncs.com:23450',
  query: {user: 'put_object'},
  body: 'bucket=${bucket}&object=${object}'
)

begin
  bucket.put_object('files/hello', file: '/tmp/x', callback: callback)
rescue Aliyun::OSS::CallbackError => e
  puts "Callback failed: #{e.message}"
end
```

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Document</title>
  </head>

  <body>
    <button id="submit">上传回调</button>
    <!--导入SDK文件-->
    <script
      type="text/javascript"
      src="https://gosspublic.alicdn.com/aliyun-oss-sdk-6.16.0.min.js"
    ></script>
    <script type="text/javascript">
      const client = new OSS({
        // yourRegion填写Bucket所在地域。以华东1（杭州）为例，yourRegion填写为oss-cn-hangzhou。
        region: "yourRegion",
        authorizationV4: true,
        // 从STS服务获取的临时访问密钥（AccessKey ID和AccessKey Secret）。
        accessKeyId: "yourAccessKeyId",
        accessKeySecret: "yourAccessKeySecret",
        // 从STS服务获取的安全令牌（SecurityToken）。
        stsToken: "yourSecurityToken",
        // 填写Bucket名称，例如examplebucket。
        bucket: "examplebucket",
      });

      const options = {
        callback: {
          // 设置回调请求的服务器地址，且要求必须为公网地址。
          url: "http://examplebucket.aliyuncs.com:23450",
          // 设置回调请求消息头中Host的值，即您的服务器配置的Host值。
          // host: 'yourHost',
          // 设置发起回调时请求body的值。
          body: "bucket=${bucket}&object=${object}&etag=${etag}&size=${size}&mimeType=${mimeType}&imageInfo.height=${imageInfo.height}&imageInfo.width=${imageInfo.width}&imageInfo.format=${imageInfo.format}&var1=${x:var1}&var2=${x:var2}",
          // 设置发起回调请求的Content-Type。
          // contentType: 'application/x-www-form-urlencoded',
          // 客户端发起回调请求时，OSS是否向通过callbackUrl指定的回源地址发送服务器名称指示SNI（Server Name Indication）
          callbackSNI: true,
          // 设置发起回调请求的自定义参数。
          customValue: {
            var1: "value1",
            var2: "value2",
          },
        },
      };
      // 获取DOM。
      const submit = document.getElementById("submit");
      // 上传回调。
      submit.addEventListener("click", () => {
        client
          .put("example.txt", new Blob(["Hello World"]), options)
          .then((r) => console.log(r));
      });
    </script>
  </body>
</html>
```

```
// 构造上传请求。
// 依次填写Bucket名称（例如examplebucket）、Object完整路径（例如exampledir/exampleobject.txt）和本地文件完整路径（例如/storage/emulated/0/oss/examplefile.txt）。
// Object完整路径中不能包含Bucket名称。
PutObjectRequest put = new PutObjectRequest("examplebucket", "exampledir/exampleobject.txt", "/storage/emulated/0/oss/examplefile.txt");

put.setCallbackParam(new HashMap<String, String>() {
    {
        put("callbackUrl", "http://oss-demo.aliyuncs.com:23450");
        put("callbackHost", "yourCallbackHost");
        put("callbackBodyType", "application/json");
        put("callbackBody", "{\"mimeType\":${mimeType},\"size\":${size}}");
    }
});

OSSAsyncTask task = oss.asyncPutObject(put, new OSSCompletedCallback<PutObjectRequest, PutObjectResult>() {
    @Override
    public void onSuccess(PutObjectRequest request, PutObjectResult result) {
        Log.d("PutObject", "UploadSuccess");

        // 只有设置了servercallback，该值才有数据。
        String serverCallbackReturnJson = result.getServerCallbackReturnBody();

        Log.d("servercallback", serverCallbackReturnJson);
    }

    @Override
    public void onFailure(PutObjectRequest request, ClientException clientExcepion, ServiceException serviceException) {
        // 异常处理。
    }
});
```

```c
#include <alibabacloud/oss/OssClient.h>
using namespace AlibabaCloud::OSS;

int main(void)
{
    /* 初始化OSS账号信息。*/
            
    /* yourEndpoint填写Bucket所在地域对应的Endpoint。以华东1（杭州）为例，Endpoint填写为https://oss-cn-hangzhou.aliyuncs.com。*/
    std::string Endpoint = "yourEndpoint";
    /* yourRegion填写Bucket所在地域对应的Region。以华东1（杭州）为例，Region填写为cn-hangzhou。*/
    std::string Region = "yourRegion";
    /* 填写Bucket名称，例如examplebucket。*/
    std::string BucketName = "examplebucket";
    /* 填写Object完整路径，完整路径中不能包含Bucket名称，例如exampledir/exampleobject.txt。*/
    std::string ObjectName = "exampledir/exampleobject.txt";
    /* 填写您的回调服务器地址。*/
    std::string ServerName = "https://example.aliyundoc.com:23450";

     /* 初始化网络等资源。*/
    InitializeSdk();

    ClientConfiguration conf;
    conf.signatureVersion = SignatureVersionType::V4;
    /* 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。*/
    auto credentialsProvider = std::make_shared<EnvironmentVariableCredentialsProvider>();
    OssClient client(Endpoint, credentialsProvider, conf);
    client.SetRegion(Region);
    std::shared_ptr<std::iostream> content = std::make_shared<std::stringstream>();
    *content << "Thank you for using Aliyun Object Storage Service!";

    /* 设置上传回调参数。*/
    std::string callbackBody = "bucket=${bucket}&object=${object}&etag=${etag}&size=${size}&mimeType=${mimeType}&my_var1=${x:var1}";
    ObjectCallbackBuilder builder(ServerName, callbackBody, "", ObjectCallbackBuilder::Type::URL);
    std::string value = builder.build();
    ObjectCallbackVariableBuilder varBuilder;
    varBuilder.addCallbackVariable("x:var1", "value1");
    std::string varValue = varBuilder.build();
    PutObjectRequest request(BucketName, ObjectName, content);
    request.MetaData().addHeader("x-oss-callback", value);
    request.MetaData().addHeader("x-oss-callback-var", varValue);
    auto outcome = client.PutObject(request);

    /* 释放网络等资源。*/
    ShutdownSdk();
    return 0;
}
```

```
OSSPutObjectRequest * request = [OSSPutObjectRequest new];
// 填写Bucket名称，例如examplebucket。
request.bucketName = @"examplebucket";
// 填写不包含Bucket名称在内的Object完整路径，例如exampledir/exampleobject.txt。
request.objectKey = @"exampledir/exampleobject.txt";
request.uploadingFileURL = [NSURL fileURLWithPath:@"<filepath>"];
// 设置回调参数
request.callbackParam = @{
                          @"callbackUrl": @"<your server callback address>",
                          @"callbackBody": @"<your callback body>"
                          };
// 设置自定义变量。
request.callbackVar = @{
                        @"<var1>": @"<value1>",
                        @"<var2>": @"<value2>"
                        };
request.uploadProgress = ^(int64_t bytesSent, int64_t totalByteSent, int64_t totalBytesExpectedToSend) {
    NSLog(@"%lld, %lld, %lld", bytesSent, totalByteSent, totalBytesExpectedToSend);
};
OSSTask * task = [client putObject:request];
[task continueWithBlock:^id(OSSTask *task) {
    if (task.error) {
        OSSLogError(@"%@", task.error);
    } else {
        OSSPutObjectResult * result = task.result;
        NSLog(@"Result - requestId: %@, headerFields: %@, servercallback: %@",
              result.requestId,
              result.httpResponseHeaderFields,
              result.serverReturnJsonString);
    }
    return nil;
}];
// 实现同步阻塞等待任务完成。
// [task waitUntilFinished];
```

```c
#include "oss_api.h"
#include "aos_http_io.h"
/* yourEndpoint填写Bucket所在地域对应的Endpoint。以华东1（杭州）为例，Endpoint填写为https://oss-cn-hangzhou.aliyuncs.com。*/
const char *endpoint = "yourEndpoint";

/* 填写Bucket名称，例如examplebucket。*/
const char *bucket_name = "examplebucket";
/* 填写Object完整路径，完整路径中不能包含Bucket名称，例如exampledir/exampleobject.txt。*/
const char *object_name = "exampledir/exampleobject.txt";
const char *object_content = "More than just cloud.";
/* yourRegion填写Bucket所在地域对应的Region。以华东1（杭州）为例，Region填写为cn-hangzhou。*/
const char *region = "yourRegion";
void init_options(oss_request_options_t *options)
{
    options->config = oss_config_create(options->pool);
    /* 用char*类型的字符串初始化aos_string_t类型。*/
    aos_str_set(&options->config->endpoint, endpoint);
    /* 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。*/    
    aos_str_set(&options->config->access_key_id, getenv("OSS_ACCESS_KEY_ID"));
    aos_str_set(&options->config->access_key_secret, getenv("OSS_ACCESS_KEY_SECRET"));
    //需要额外配置以下两个参数
    aos_str_set(&options->config->region, region);
    options->config->signature_version = 4;
    /* 是否使用了CNAME。0表示不使用。*/
    options->config->is_cname = 0;
    /* 设置网络相关参数，比如超时时间等。*/
    options->ctl = aos_http_controller_create(options->pool, 0);
}
int main(int argc, char *argv[])
{
    aos_pool_t *p = NULL;
    aos_status_t *s = NULL;
    aos_string_t bucket;
    aos_string_t object;
    aos_table_t *headers = NULL;
    oss_request_options_t *options = NULL;
    aos_table_t *resp_headers = NULL;
    aos_list_t resp_body;
    aos_list_t buffer;
    aos_buf_t *content;
    char *buf = NULL;
    int64_t len = 0;
    int64_t size = 0;
    int64_t pos = 0;
    char b64_buf[1024];
    int b64_len;
    /* 采用JSON格式。*/
    /*（可选）设置回调请求消息头中Host的值，如您的服务器配置Host的值。*/
    char *callback =  "{"
        "\"callbackUrl\":\"http://oss-demo.aliyuncs.com:23450\","
         "\"callbackHost\":\"yourCallbackHost\","
        "\"callbackBody\":\"bucket=${bucket}&object=${object}&size=${size}&mimeType=${mimeType}\","
        "\"callbackBodyType\":\"application/x-www-form-urlencoded\""
        "}";
    /* 在程序入口调用aos_http_io_initialize方法来初始化网络、内存等全局资源。*/
    if (aos_http_io_initialize(NULL, 0) != AOSE_OK) {
        exit(1);
    }
    /* 初始化参数。*/
    aos_pool_create(&p, NULL);
    options = oss_request_options_create(p);
    init_options(options);
    aos_str_set(&bucket, bucket_name);
    aos_str_set(&object, object_name);
    aos_list_init(&resp_body);
    aos_list_init(&buffer);
    content = aos_buf_pack(options->pool, object_content, strlen(object_content));
    aos_list_add_tail(&content->node, &buffer);
    /* 将callback放入header。*/
    b64_len = aos_base64_encode((unsigned char*)callback, strlen(callback), b64_buf);
    b64_buf[b64_len] = '\0';
    headers = aos_table_make(p, 1);
    apr_table_set(headers, OSS_CALLBACK, b64_buf);
    /* 上传回调。*/
    s = oss_do_put_object_from_buffer(options, &bucket, &object, &buffer,
        headers, NULL, NULL, &resp_headers, &resp_body);
    if (aos_status_is_ok(s)) {
        printf("put object from buffer succeeded\n");
    } else {
        printf("put object from buffer failed\n");
    }
    /* 获取buffer长度。*/
    len = aos_buf_list_len(&resp_body);
    buf = (char *)aos_pcalloc(p, (apr_size_t)(len + 1));
    buf[len] = '\0';
    /* 拷贝buffer内容到内存。*/
    aos_list_for_each_entry(aos_buf_t, content, &resp_body, node) {
        size = aos_buf_size(content);
        memcpy(buf + pos, content->pos, (size_t)size);
        pos += size;
    }
    /* 释放内存池，相当于释放了请求过程中各资源分配的内存。*/
    aos_pool_destroy(p);
    /* 释放之前分配的全局资源。*/
    aos_http_io_deinitialize();
    return 0;
}
```

### 使用命令行工具ossutil

使用 [put-object](https://help.aliyun.com/zh/oss/developer-reference/put-object) 前，确保已 [安装ossutil](https://help.aliyun.com/zh/oss/install-ossutil2#DAS) 。

#### 使用示例

- 以字符串的形式上传文件。
	```bash
	ossutil api put-object --bucket examplebucket --key exampleobject --body "hi oss"
	```
- 以文件的形式上传。
	```bash
	ossutil api put-object --bucket examplebucket --key exampleobject --body file://uploadFile
	```
- 以字符串的形式上传文件并携带自定义元数据。
	```bash
	ossutil api put-object --bucket examplebucket --key exampleobject  --metadata user=aliyun --metadata email=ali***@aliyuncs.com --body "hi oss"
	```
- 以字符串的形式上传文件并指定object的标签信息。
	```bash
	ossutil api put-object --bucket examplebucket --key exampleobject --body "hi oss" --tagging "TagA=A&TagB=B"
	```
- 以字符串的形式上传文件并指定object的访问权限以及存储类型。
	```bash
	ossutil api put-object --bucket examplebucket --key exampleobject --body "hi oss" --object-acl private --storage-class IA
	```
- 以字符串的形式上传文件并指定object服务端加密方式。
	```bash
	ossutil api put-object --bucket examplebucket --key exampleobject --body "hi oss" --server-side-encryption KMS --server-side-data-encryption SM4 --server-side-encryption-key-id 9468da86-3509-4f8d-a61e-6eab1eac****
	```
- 以字符串的形式上传文件并禁止覆盖同名Object。
	```bash
	ossutil api put-object --bucket examplebucket --key exampleobject --body "hi oss" --forbid-overwrite true
	```
- 以字符串的形式上传文件并指定该Object被下载时网页的缓存行为。
	```bash
	ossutil api put-object --bucket examplebucket --key exampleobject --body "hi oss" --cache-control no-cache
	```
- 以字符串的形式上传文件并指定该Object被下载时的名称。
	```bash
	ossutil api put-object --bucket examplebucket --key exampleobject --body "hi oss" --content-disposition "attachment;filename=oss_download.jpg"
	```

## 相关API

以上操作方式底层基于API实现，如果您的程序自定义要求较高，您可以直接发起REST API请求。直接发起REST API请求需要手动编写代码计算签名。更多信息，请参见 [PutObject](https://help.aliyun.com/zh/oss/developer-reference/putobject) 。

## 权限说明

阿里云账号默认拥有全部权限。阿里云账号下的RAM用户或RAM角色默认没有任何权限，需要阿里云账号或账号管理员通过 [RAM Policy概述](https://help.aliyun.com/zh/oss/ram-policy-overview/) 或 [Bucket Policy](https://help.aliyun.com/zh/oss/user-guide/oss-bucket-policy/) 授予操作权限。

<table><tbody><tr><td rowspan="1" colspan="1"><p><b>API</b></p></td><td rowspan="1" colspan="1"><p><b>Action</b></p></td><td rowspan="1" colspan="1"><p><b>说明</b></p></td></tr><tr><td rowspan="4" colspan="1"><p>PutObject</p></td><td rowspan="1" colspan="1"><p><code>oss:PutObject</code></p></td><td rowspan="1" colspan="1"><p>上传Object。</p></td></tr><tr><td rowspan="1" colspan="1"><p><code>oss:PutObjectTagging</code></p></td><td rowspan="1" colspan="1"><p>上传Object时，如果通过x-oss-tagging指定Object的标签，则需要此操作的权限。</p></td></tr><tr><td rowspan="1" colspan="1"><p><code>kms:GenerateDataKey</code></p></td><td rowspan="2" colspan="1"><p>上传Object时，如果Object的元数据包含X-Oss-Server-Side-Encryption: KMS，则需要这两个操作的权限。</p></td></tr><tr><td rowspan="1" colspan="1"><p><code>kms:Decrypt</code></p></td></tr></tbody></table>

## 计费说明

通过简单上传方式将文件上传到OSS，会产生以下计费项。有关计费项的定价详情，请参见 [OSS产品定价](https://www.aliyun.com/price/product?spm=a2c4g.11186623.0.0.628c4d22ZdP2B0#/oss/detail/oss) 。

<table><tbody><tr><td rowspan="1" colspan="1"><p><b>API</b></p></td><td rowspan="1" colspan="1"><p><b>计费项</b></p></td><td rowspan="1" colspan="1"><p><b>说明</b></p></td></tr><tr><td rowspan="2" colspan="1"><p>PutObject</p></td><td rowspan="1" colspan="1"><p>PUT类型请求</p></td><td rowspan="1" colspan="1"><p>根据成功的请求次数计算请求费用。</p></td></tr><tr><td rowspan="1" colspan="1"><p>存储费用</p></td><td rowspan="1" colspan="1"><p>根据Object的存储类型、大小和时长收取存储费用。</p></td></tr></tbody></table>

## 常见问题

### 如何上传超过5GB的文件？

简单上传的文件大小限制为5GB。对于超过5GB的文件，请使用 [分片上传](https://help.aliyun.com/zh/oss/user-guide/multipart-upload#concept-wzs-2gb-5db) 。

### 如何批量上传？

- **使用OSS控制台（支持手动筛选文件）**
	单击目标Bucket名称进入Bucket，单击 **上传文件** > **扫描文件夹** ，选中待上传的文件夹后，移除不需要的文件，单击 **上传文件** 即可。
	![image](https://help-static-aliyun-doc.aliyuncs.com/assets/img/zh-CN/3093288371/p908168.png)
- **使用ossbrowser（不支持筛选文件）**
	单击目标Bucket名称进入Bucket，单击页面上方 **上传** 按钮，在下拉列表框中选择上传文件夹。
	![image](https://help-static-aliyun-doc.aliyuncs.com/assets/img/zh-CN/4093288371/p908178.png)
- **使用ossutil工具（支持根据文件名筛选）**
	使用ossutil工具的cp命令，结合-r（--recursive）选项，可批量上传文件到OSS，并支持通过 --include 和 --exclude 选项按文件名进行筛选。详情请参见 [cp（上传文件）](https://help.aliyun.com/zh/oss/developer-reference/cp-upload-file) 。
	- 将本地文件夹localfolder中的文件上传至examplebucket中的desfolder文件夹下。
		```bash
		ossutil cp -r D:/localpath/localfolder/ oss://examplebucket/desfolder/
		```
		- 批量上传符合条件的文件。
		上传所有文件格式为TXT的文件。
		```bash
		ossutil cp -r D:/localpath/localfolder/ oss://examplebucket/desfolder/ --include "*.txt"
		```
- **ZIP包解压**
	使用ZIP包解压功能，先配置解压规则，然后将多个文件打包成ZIP包上传到OSS。此时将触发函数计算进行解压并将解压后的文件传回OSS，实现批量上传。详情请参见 [上传ZIP包并自动解压](https://help.aliyun.com/zh/oss/user-guide/zip-package-decompression) 。

### 如何将OSS资源分享给第三方临时访问？

OSS 提供两种方式供第三方临时访问：

- 预签名URL
	如果您仅需要第三方对指定文件进行临时上传或下载，预签名URL便可满足您的需求，详细使用方法请参见 [使用预签名URL上传文件](https://help.aliyun.com/zh/oss/user-guide/upload-files-using-presigned-urls) 、 [使用预签名URL下载文件](https://help.aliyun.com/zh/oss/user-guide/how-to-obtain-the-url-of-a-single-object-or-the-urls-of-multiple-objects#de0e3ab64803f) 。
- STS临时访问凭证
	如果您希望第三方对OSS的操作不只局限于上传、下载，而是可以执行例如：列举文件、拷贝文件等更多OSS资源的管理操作，建议您了解并使用STS临时访问凭证，详情请参见 [使用STS临时访问凭证访问OSS](https://help.aliyun.com/zh/oss/developer-reference/use-temporary-access-credentials-provided-by-sts-to-access-oss) 。

### 如何处理上传后的文件？

- **图片处理：** 对上传的图片进行压缩、添加自定义样式、获取图片大小信息等操作，请参见 [图片处理](https://help.aliyun.com/zh/oss/user-guide/overview-17/) 。
- **媒体处理：** 对上传的图片或者视频等进行文字识别、字幕提取、视频转码、生成视频封面等处理，请参见 [媒体处理](https://help.aliyun.com/zh/mps/product-overview/features) 。
- **文档预览和编辑：** 如果您希望对上传的PDF、PPT、Word等格式的文档进行在线预览或在线编辑，请参见 [WebOffice预览和协作编辑](https://help.aliyun.com/zh/imm/getting-started/weboffice-preview-and-collaborative-editing) 。

### 如何使用自定义域名进行简单上传？

在使用SDK创建OssClient时，请改用自定义域名，具体操作可参考 [通过自定义域名访问OSS](https://help.aliyun.com/zh/oss/user-guide/access-buckets-via-custom-domain-names#4b2dbc90796li) 的SDK。请注意，各语言的配置中，cname参数需设置为true。

### 如何防止文件被意外覆盖？

简单上传默认会覆盖同名Object，您可以选择以下任意方式防止Object被意外覆盖。

- 开启版本控制功能
	开启版本控制功能后，被覆盖的Object会以历史版本的形式保存下来。您可以随时恢复历史版本Object。更多信息，请参见 [版本控制介绍](https://help.aliyun.com/zh/oss/user-guide/overview-78/#concept-jdg-4rx-bgb) 。
- 在上传请求中携带禁止覆盖同名Object的参数
	在上传请求的Header中携带参数x-oss-forbid-overwrite，并指定其值为true。当您上传的Object在OSS中存在同名Object时，该Object会上传失败，并返回 `FileAlreadyExists` 错误。当不携带此参数或此参数的值为false时，同名Object会被覆盖。

### 如何降低PUT类请求费用？

如果要上传的文件数量较多，直接指定上传的文件类型为深度冷归档类型会造成较高的 [PUT类请求费用](https://www.aliyun.com/price/product?spm=a2c4g.59636.0.0.5c844b78MdkEAN&5176.7933691.744462.price2.b7a36a56kldoxf#/oss/detail/ossbag) 。建议您先将文件的存储类型指定为标准存储进行上传，然后通过 [生命周期规则](https://help.aliyun.com/zh/oss/user-guide/lifecycle-rules-based-on-the-last-modified-time#concept-y2g-szy-5db) 将其转储为深度冷归档类型，从而降低PUT类请求费用。

### 多个用户上传同名（含路径）的文件，OSS会如何保留？

这取决于是否开启了 [版本控制](https://help.aliyun.com/zh/oss/user-guide/overview-78/#concept-jdg-4rx-bgb) ：

![image](https://help-static-aliyun-doc.aliyuncs.com/assets/img/zh-CN/9185809771/CAEQVRiBgIDx3azKrBkiIDFhZTMyNjQxZGFmMzRmMzA5YTA4ZDIyNzQ4ZTBkYTkw4940965_20250220112557.441.svg)
- **在版本控制未开启或暂停时：** 若有多个用户上传同名Object，后上传完成的Object会覆盖前一个，并只保留最后上传完成的Object。例如，用户A在用户B之后完成上传，最终将保留用户A上传的Object。
- **版本控制开启时：** 每次上传同名Object都会创建新版本，并用版本ID（Version ID）标识。OSS根据上传的开始时间确定最新版本。例如，用户B在用户A之后开始上传，则用户B上传的Object将被标记为最新版本。

### 如何调优上传性能？

如果您在上传大量Object时，在命名上使用了顺序前缀（如时间戳或字母顺序），可能会出现大量Object索引集中存储于存储空间中某个特定分区的情况，进而导致请求速率下降。建议您在上传大量Object时，不要使用顺序前缀的Object名称，而是将顺序前缀改为随机性前缀。具体操作，请参见 [OSS性能最佳实践](https://help.aliyun.com/zh/oss/user-guide/oss-performance-best-practices/#concept-xtt-pln-vdb) 。